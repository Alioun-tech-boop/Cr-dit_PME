"""Outbox locale ; aucun identifiant de destination n'est fourni par le client."""

import argparse
import time
from sqlalchemy import select
from credit.persistence import sessions, now
from credit.partners.models import Outbox
from credit.partners.delivery import dispatch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=2)
    args = parser.parse_args()
    if not 0.5 <= args.interval <= 30:
        parser.error("Intervalle : 0,5 à 30 secondes")
    _, factory = sessions()
    while True:
        with factory() as session:
            ids = session.scalars(
                select(Outbox.transmission_id)
                .where(Outbox.state.in_(["pending", "processing"]), Outbox.due_at <= now())
                .limit(20)
            ).all()
            for id in ids:
                dispatch(session, id)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
