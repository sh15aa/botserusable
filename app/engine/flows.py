import re
import logging
from typing import Dict, Any, Optional, Callable, List
from pydantic import BaseModel
from app.schemas.unmp import UnifiedMessage, UnifiedResponse, ButtonAction
from app.engine.fsm import ConversationContext

logger = logging.getLogger(__name__)


class FlowStep(BaseModel):
    id: str
    prompt_text: str
    options: Optional[List[ButtonAction]] = None
    validation_regex: Optional[str] = None
    error_message: Optional[str] = None
    next_step_id: Optional[str] = None


class FlowDefinition(BaseModel):
    flow_id: str
    initial_step_id: str
    steps: Dict[str, FlowStep]


class FlowEngine:
    """
    Stateful multi-step form and workflow engine.
    Stores partial form answers in ConversationContext.state_data.
    """
    def __init__(self):
        self.flows: Dict[str, FlowDefinition] = {}

    def register_flow(self, flow: FlowDefinition):
        self.flows[flow.flow_id] = flow

    async def start_flow(
        self,
        flow_id: str,
        context: ConversationContext,
        message: UnifiedMessage
    ) -> Optional[UnifiedResponse]:
        flow = self.flows.get(flow_id)
        if not flow:
            logger.error(f"Flow {flow_id} not registered.")
            return None

        context.current_state = f"FLOW:{flow_id}"
        context.state_data["active_flow_id"] = flow_id
        context.state_data["current_step_id"] = flow.initial_step_id
        context.state_data["form_answers"] = {}

        initial_step = flow.steps[flow.initial_step_id]
        return UnifiedResponse(
            recipient_channel_user_id=message.channel_user_id,
            channel=message.channel,
            text=initial_step.prompt_text,
            buttons=initial_step.options,
        )

    async def handle_flow_input(
        self,
        context: ConversationContext,
        message: UnifiedMessage
    ) -> Optional[UnifiedResponse]:
        active_flow_id = context.state_data.get("active_flow_id")
        current_step_id = context.state_data.get("current_step_id")
        flow = self.flows.get(active_flow_id)

        if not flow or not current_step_id or current_step_id not in flow.steps:
            context.current_state = "IDLE"
            return UnifiedResponse(
                recipient_channel_user_id=message.channel_user_id,
                channel=message.channel,
                text="Form session expired. Returning to main menu.",
            )

        step = flow.steps[current_step_id]
        user_val = message.content.action_payload or message.content.text or ""

        # Validate input against regex if defined
        if step.validation_regex:
            if not re.match(step.validation_regex, user_val.strip()):
                return UnifiedResponse(
                    recipient_channel_user_id=message.channel_user_id,
                    channel=message.channel,
                    text=step.error_message or "Invalid input. Please try again:",
                    buttons=step.options,
                )

        # Record answer
        context.state_data.setdefault("form_answers", {})[step.id] = user_val.strip()

        # Advance to next step or complete
        if step.next_step_id and step.next_step_id in flow.steps:
            next_step = flow.steps[step.next_step_id]
            context.state_data["current_step_id"] = next_step.id
            return UnifiedResponse(
                recipient_channel_user_id=message.channel_user_id,
                channel=message.channel,
                text=next_step.prompt_text,
                buttons=next_step.options,
            )
        else:
            # Flow Completed
            answers = context.state_data.get("form_answers", {})
            context.current_state = "IDLE"
            context.state_data["last_completed_flow"] = active_flow_id
            context.state_data.pop("active_flow_id", None)
            context.state_data.pop("current_step_id", None)

            return UnifiedResponse(
                recipient_channel_user_id=message.channel_user_id,
                channel=message.channel,
                text=f"✅ Thank you! Your submission has been received.",
                buttons=[
                    ButtonAction(id="MENU_MAIN", title="Main Menu")
                ]
            )
