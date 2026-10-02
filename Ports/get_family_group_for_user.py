"""Conservative identity binding. JWT claims alone never prove authentication."""
import base64
import json
import time
from config import valid_steamid
from error_handler import Failure
from Ports.request_executor import RequestSpec, object_at, Result


def token_subject(token):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        if not isinstance(payload, dict) or not valid_steamid(payload.get("sub")):
            return None
        if type(payload.get("exp")) not in (int, float) or payload["exp"] <= time.time():
            raise Failure("AUTH_EXPIRED", "Session expiration claim has elapsed", source="auth")
        return payload["sub"]
    except (ValueError, UnicodeError, TypeError):
        return None


async def call(executor, params, context):
    try:
        subject = token_subject(executor.config.family_token)
        if subject != params["steamid"]:
            raise Failure("ACCESS_DENIED", "Session subject is unconfirmed or differs from target; family source not bound", source="auth")
    except Failure as exc:
        return Result("unavailable", error=exc.info, source="get_family_group_for_user")
    def decode(body):
        data = object_at(body, "response")
        # Steam accepts the token; the local claim check only prevents a cross-account request.
        if data.get("is_not_member_of_any_group") is True:
            return dict(_state="not_applicable", no_family=True, identity_evidence="matching token subject and accepted authenticated request", complete=True)
        groupid = str(data.get("family_groupid", ""))
        group = data.get("family_group", {})
        members = group.get("members") if isinstance(group, dict) else None
        if not groupid.isdigit() or int(groupid) <= 0 or not isinstance(members, list):
            raise Failure("DATA_UNAVAILABLE", "Family identity or membership cannot be confirmed")
        ids = [str(m.get("steamid")) for m in members if isinstance(m, dict)]
        if params["steamid"] not in ids or not all(valid_steamid(s) for s in ids):
            raise Failure("ACCESS_DENIED", "Target absent from returned family members")
        return dict(family_groupid=groupid, member_steamids=ids, subject_steamid=subject, complete=True,
                    identity_evidence="matching token subject, accepted authenticated request and returned membership")
    return await executor.execute(RequestSpec("get_family_group_for_user", "https://api.steampowered.com/IFamilyGroupsService/GetFamilyGroupForUser/v1/",
        {"input_json": json.dumps({"steamid": params["steamid"], "include_family_group_response": True})}, "session_token", True), decode, context)
