import argparse

from sqlalchemy import func
from sqlmodel import Session, select

from app.database import engine
from app.models.access import AccessAuditEvent
from app.models.user import User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    arguments = parser.parse_args()
    with Session(engine) as session:
        session.exec(select(User).order_by(User.id).with_for_update()).all()
        if session.exec(select(User).where(User.is_global_admin == True, User.is_active == True)).first():
            raise SystemExit("An active global administrator already exists. Use the administration screen.")
        user = session.exec(select(User).where(func.lower(User.email) == arguments.email.lower())).first()
        if user is None or not user.is_active:
            raise SystemExit("An active existing account is required")
        user.is_global_admin = True
        session.add(user)
        session.add(AccessAuditEvent(actor_user_id=user.id, resource_type="users", resource_id=user.id, action="bootstrap_global_admin", changed_fields=["is_global_admin"]))
        session.commit()
        print("Global administrator profile activated")


if __name__ == "__main__":
    main()
