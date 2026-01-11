"""Security module for Telegram Bot access control."""
from telegram import Update


def is_user_allowed(user_id: int, whitelist: list[int | str]) -> bool:
    """Check if user is in whitelist.

    Args:
        user_id: Telegram user ID to check.
        whitelist: List of allowed user IDs, or ['all'] to allow everyone.

    Returns:
        True if user is allowed, False otherwise.
    """
    if 'all' in whitelist:
        return True
    return user_id in whitelist


def should_leave_group(update: Update, whitelist: list[int | str]) -> bool:
    """Check if bot should leave a group based on who added it.

    Args:
        update: Telegram Update object with my_chat_member event.
        whitelist: List of allowed user IDs who can add bot to groups.

    Returns:
        True if bot should leave (added by unauthorized user), False otherwise.
    """
    if not update.my_chat_member:
        return False

    member_update = update.my_chat_member
    old_status = member_update.old_chat_member.status
    new_status = member_update.new_chat_member.status

    # Bot being added to group (status changed from left/kicked to member/administrator)
    if old_status in ('left', 'kicked') and new_status in ('member', 'administrator'):
        inviter_id = member_update.from_user.id
        return not is_user_allowed(inviter_id, whitelist)

    return False
