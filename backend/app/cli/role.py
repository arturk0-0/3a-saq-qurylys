"""Operator-only command; never exposes an endpoint for self-assignment of roles."""

import argparse

from firebase_admin import auth

from app.core.config import Settings
from app.core.firebase import FirebaseRuntime


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set analyst/admin custom claims on an existing user"
    )
    parser.add_argument("uid")
    parser.add_argument("role", choices=["analyst", "admin"])
    parser.add_argument("--project-confirm", required=True)
    args = parser.parse_args()
    settings = Settings()
    if args.project_confirm != settings.firebase_project_id:
        parser.error("Project confirmation does not match FIREBASE_PROJECT_ID")
    runtime = FirebaseRuntime(settings)
    try:
        app = runtime.app()
        user = auth.get_user(args.uid, app=app)
        claims = {**(user.custom_claims or {}), "role": args.role}
        auth.set_custom_user_claims(user.uid, claims, app=app)
        auth.revoke_refresh_tokens(user.uid, app=app)
        print("Role updated. The user must sign in again.")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
