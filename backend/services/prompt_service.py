from backend.prompts.landing_zone import build_landing_zone_prompt
from backend.exceptions.api_exception import ApiException

class PromptService:

    def build_prompt(self, request):

        if request.template == "landing-zone":
            return build_landing_zone_prompt(request)

        raise ApiException(
              message=f"Unknown template: {request.template}",
              status_code=400
        )