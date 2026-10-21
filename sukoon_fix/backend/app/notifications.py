"""Sukoon — family notification fan-out.

A family member can choose, on their dashboard, whether they want every
small update (a missed water reminder, a mood check-in) or only the
safety-significant ones (left the safe zone, an alert was resolved, a new
diagnosis was added, a help/comfort call was made). This module is the one
place that fan-out happens, so every caller just says "this happened, and
here's whether it's important" — the family member's own preference decides
whether they actually see it.
"""
from sqlalchemy.orm import Session

from . import models


def notify_family(db: Session, patient_id: str, title: str, body: str,
                   category: str = "update", important: bool = False):
    """Create a Notification for every family member linked to this patient,
    honoring each one's notification_preference: 'all' always receives it,
    'important' only receives it when `important` is True."""
    links = (
        db.query(models.PatientFamilyRelationship)
        .filter(models.PatientFamilyRelationship.patient_id == patient_id)
        .all()
    )
    if not links:
        return
    for link in links:
        fam = db.query(models.FamilyMember).filter(models.FamilyMember.id == link.family_member_id).first()
        if not fam:
            continue
        pref = fam.notification_preference or "important"
        if pref == "all" or important:
            db.add(models.Notification(user_id=fam.user_id, title=title, body=body, category=category))
    db.commit()
