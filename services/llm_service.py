"""
LLMService v2 — Multi-provider LLM with fallback chain.
Keys stored in SQLite. Supports NVIDIA NIM + OpenAI + any OpenAI-compatible.
"""
import asyncio, time, logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict
from datetime import datetime
import pytz

from llm_engine import (
    NVIDIANimClient, get_nim_client,
    generate_trade_commentary, generate_btst_narrative,
    interpret_breaking_news, explain_alert,
    PRIMARY_MODEL, FAST_MODEL, NVIDIA_NIM_BASE_URL,
)

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="llm")

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class LLMProvider:
    """Single LLM provider instance."""
    def __init__(self, db_id, provider, label, api_key, base_url=None,
                 model=None, priority=1, rate_limit_rpm=40):
        self.db_id = db_id
        self.provider = provider
        self.label = label
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.priority = priority
        self.client = None
        self.available = False
        self.total_calls = 0
        self.total_errors = 0
        self.last_error = ""
        self._last_call_time = 0
        self._min_interval = 60.0 / max(rate_limit_rpm, 1)
        self._init_client()

    def _init_client(self):
        if not HAS_OPENAI:
            return
        try:
            if self.provider == "nvidia_nim":
                self.client = OpenAI(base_url=self.base_url or NVIDIA_NIM_BASE_URL, api_key=self.api_key)
                self.model = self.model or PRIMARY_MODEL
            elif self.provider == "openai":
                self.client = OpenAI(api_key=self.api_key)
                self.model = self.model or "gpt-4o-mini"
            elif self.provider == "openai_compatible":
                if not self.base_url: return
                self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)
                self.model = self.model or "default"
            self.available = True
            logger.info(f"LLM [{self.label}] {self.provider} → {self.model}")
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Failed [{self.label}]: {e}")

    def chat(self, system_prompt, user_message, temperature=0.1, max_tokens=512):
        if not self.available or not self.client:
            return None
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()
        try:
            r = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role":"system","content":system_prompt},{"role":"user","content":user_message}],
                temperature=temperature, max_tokens=max_tokens, stream=False,
            )
            self.total_calls += 1
            return r.choices[0].message.content.strip()
        except Exception as e:
            self.total_errors += 1
            self.last_error = str(e)[:200]
            logger.warning(f"[{self.label}] failed: {e}")
            return None


class LLMService:
    """Multi-provider LLM service with DB-backed keys and fallback chain."""
    def __init__(self):
        self._providers: List[LLMProvider] = []
        self._nim_client: Optional[NVIDIANimClient] = None
        self._loaded = False

    def load_keys_from_db(self):
        try:
            from core.database import SessionLocal
            from models.api_key import APIKey
            db = SessionLocal()
            try:
                keys = db.query(APIKey).filter(APIKey.is_active == True).order_by(APIKey.priority.asc()).all()
                self._providers = []
                for k in keys:
                    p = LLMProvider(db_id=k.id, provider=k.provider, label=k.label,
                                    api_key=k.api_key, base_url=k.base_url, model=k.model,
                                    priority=k.priority, rate_limit_rpm=k.rate_limit_rpm or 40)
                    if p.available:
                        self._providers.append(p)
                self._loaded = True
                logger.info(f"Loaded {len(self._providers)} LLM providers from DB")
                nim = [p for p in self._providers if p.provider == "nvidia_nim"]
                if nim:
                    self._nim_client = get_nim_client(nim[0].api_key)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to load API keys: {e}")

    def reload_keys(self):
        self.load_keys_from_db()

    @property
    def providers(self):
        return [{"db_id":p.db_id,"provider":p.provider,"label":p.label,"model":p.model,
                 "priority":p.priority,"available":p.available,"calls":p.total_calls,
                 "errors":p.total_errors,"last_error":p.last_error} for p in self._providers]

    @property
    def available(self):
        return any(p.available for p in self._providers)

    def get_client(self):
        if not self._loaded: self.load_keys_from_db()
        return self._nim_client

    def _update_stats(self, provider):
        try:
            from core.database import SessionLocal
            from models.api_key import APIKey
            db = SessionLocal()
            try:
                k = db.query(APIKey).filter(APIKey.id == provider.db_id).first()
                if k:
                    k.total_calls = provider.total_calls
                    k.total_errors = provider.total_errors
                    k.last_used_at = datetime.now(IST).isoformat()
                    if provider.last_error: k.last_error = provider.last_error
                    db.commit()
            finally:
                db.close()
        except: pass

    async def generate_trade_commentary(self, symbol, price, signal_label, score,
                                         action, strike, indicator_signals, global_label, vix, pcr):
        client = self.get_client()
        if not client or not client.available: return None
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(_executor, generate_trade_commentary,
                client, symbol, price, signal_label, score, action, strike,
                indicator_signals, global_label, vix, pcr)
        except: return None

    async def generate_btst_narrative(self, prediction, score, confidence, factors):
        client = self.get_client()
        if not client or not client.available: return None
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(_executor, generate_btst_narrative,
                client, prediction, score, confidence, factors)
        except: return None

    async def interpret_breaking_news(self, headline):
        client = self.get_client()
        if not client or not client.available: return None
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(_executor, interpret_breaking_news, client, headline)
        except: return None

    async def explain_alert(self, alert):
        client = self.get_client()
        if not client or not client.available: return None
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(_executor, explain_alert, client, alert)
        except: return None

    def test_key(self, provider, api_key, base_url=None, model=None):
        start = time.time()
        try:
            p = LLMProvider(db_id=0, provider=provider, label="test",
                            api_key=api_key, base_url=base_url, model=model)
            if not p.available:
                return {"success":False,"error":"Failed to init client","latency_ms":0}
            result = p.chat("Reply with exactly: OK","Test. Reply OK.",max_tokens=10)
            ms = int((time.time()-start)*1000)
            if result:
                return {"success":True,"provider":provider,"model_used":p.model,
                        "response_preview":result[:50],"latency_ms":ms,"error":""}
            return {"success":False,"provider":provider,"model_used":p.model,
                    "latency_ms":ms,"error":p.last_error or "No response"}
        except Exception as e:
            return {"success":False,"provider":provider,"error":str(e)[:200],
                    "latency_ms":int((time.time()-start)*1000)}


llm_service = LLMService()
