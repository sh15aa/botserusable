import logging
from typing import Optional, List, Dict, Any
from openai import AsyncOpenAI
from app.ai.guardrails import AIGuardrailService
from app.ai.memory import ConversationMemory

logger = logging.getLogger(__name__)


class LLMGateway:
    def __init__(
        self,
        api_key: Optional[str],
        default_model: str = "gpt-4o-mini",
        memory: Optional[ConversationMemory] = None,
    ):
        self.api_key = api_key
        self.default_model = default_model
        self.memory = memory
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None

    async def generate_response(
        self,
        user_id: str,
        user_text: str,
        system_prompt: str = "You are a helpful, courteous customer support bot."
    ) -> str:
        """
        Executes guarded LLM inference with Canary Token injection and memory tracking.
        """
        if not self.client:
            return "AI service is currently not configured."

        # 1. Canary Token & Guardrail Sanitization
        canary_token = AIGuardrailService.generate_canary_token()
        safe_sys, safe_user = AIGuardrailService.prepare_secure_prompt(
            base_system_prompt=system_prompt,
            user_input=user_text,
            canary_token=canary_token,
        )

        # 2. Retrieve Conversation Memory
        messages: List[Dict[str, str]] = [{"role": "system", "content": safe_sys}]
        if self.memory:
            history = await self.memory.get_history(user_id)
            messages.extend(history)

        messages.append({"role": "user", "content": safe_user})

        try:
            # 3. Model Inference
            response = await self.client.chat.completions.create(
                model=self.default_model,
                messages=messages,
                temperature=0.7,
                max_tokens=500,
            )

            raw_reply = response.choices[0].message.content or ""

            # 4. Output Validation & Leak Defense
            is_valid, clean_reply = AIGuardrailService.validate_and_sanitize_output(
                raw_output=raw_reply,
                canary_token=canary_token,
            )

            if not is_valid:
                logger.warning(f"Potential canary leakage or jailbreak output blocked for user {user_id}")
                return clean_reply

            # 5. Persist to Memory
            if self.memory:
                await self.memory.append_turn(user_id, "user", user_text)
                await self.memory.append_turn(user_id, "assistant", clean_reply)

            return clean_reply

        except Exception as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            return "I apologize, but I encountered an error while generating a response. Please try again later."
