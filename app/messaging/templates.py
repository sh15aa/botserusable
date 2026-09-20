import re
from typing import Dict, Any, Optional


class TemplateEngine:
    def __init__(self):
        # Format: { template_name: { locale: template_text } }
        self.templates: Dict[str, Dict[str, str]] = {
            "welcome": {
                "en": "👋 Hello {{name}}! Welcome to {{bot_name}}. How can I assist you today?",
                "es": "👋 ¡Hola {{name}}! Bienvenido a {{bot_name}}. ¿Cómo puedo ayudarte hoy?",
                "hi": "👋 नमस्ते {{name}}! {{bot_name}} में आपका स्वागत है। मैं आपकी क्या मदद कर सकता हूँ?"
            },
            "order_status": {
                "en": "📦 Order #{{order_id}}: Status is {{status}}. Expected delivery: {{eta}}.",
                "es": "📦 Pedido #{{order_id}}: El estado es {{status}}. Entrega estimada: {{eta}}.",
            },
            "payment_success": {
                "en": "✅ Payment of {{amount}} received! Thank you for your subscription.",
                "es": "✅ ¡Pago de {{amount}} recibido! Gracias por su suscripción.",
            }
        }

    def register_template(self, name: str, locale: str, content: str):
        if name not in self.templates:
            self.templates[name] = {}
        self.templates[name][locale] = content

    def render(self, template_name: str, locale: str = "en", variables: Optional[Dict[str, Any]] = None) -> str:
        """
        Renders a template with variable substitution and locale fallback.
        """
        template_group = self.templates.get(template_name, {})
        text = template_group.get(locale) or template_group.get("en", f"[Missing template: {template_name}]")

        if not variables:
            return text

        def replace_var(match):
            var_name = match.group(1).strip()
            return str(variables.get(var_name, f"{{{{{var_name}}}}}"))

        return re.sub(r"\{\{([a-zA-Z0-9_]+)\}\}", replace_var, text)
