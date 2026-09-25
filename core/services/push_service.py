import json
import logging
from django.conf import settings
from users.models import PushSubscription

try:
    from pywebpush import webpush, WebPushException
    PYWEBPUSH_AVAILABLE = True
except ImportError:
    webpush = None
    WebPushException = Exception
    PYWEBPUSH_AVAILABLE = False

logger = logging.getLogger(__name__)


def send_order_push_notification(restaurant_id, title, message, url="/orders"):
    """
    Send Web Push Notification to all subscribed devices for a given restaurant
    """
    if not PYWEBPUSH_AVAILABLE:
        logger.warning("[Web Push] pywebpush library is not installed or available.")
        return

    try:
        subscriptions = PushSubscription.objects.filter(restaurant_id=str(restaurant_id))
        if not subscriptions.exists():
            logger.info(f"[Web Push] No push subscriptions found for restaurant_id: {restaurant_id}")
            return

        payload = json.dumps({
            "title": title,
            "body": message,
            "icon": "/icons/icon-192x192.png",
            "badge": "/icons/icon-192x192.png",
            "data": { "url": url }
        })

        vapid_private_key = getattr(settings, 'VAPID_PRIVATE_KEY', None)
        vapid_email = getattr(settings, 'VAPID_ADMIN_EMAIL', 'admin@restromind.ai')

        if not vapid_private_key:
            logger.warning("[Web Push] VAPID_PRIVATE_KEY is not set in Django settings.")
            return

        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {
                            "p256dh": sub.p256dh,
                            "auth": sub.auth
                        }
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims={"sub": f"mailto:{vapid_email}"}
                )
                logger.info(f"[Web Push] Notification delivered to {sub.endpoint[:30]}...")
            except WebPushException as ex:
                logger.warning(f"[Web Push Exception] {ex}")
                # Clean up expired / unsubscribed push endpoints (HTTP 404 or 410)
                if hasattr(ex, 'response') and ex.response and ex.response.status_code in [404, 410]:
                    sub.delete()
                    logger.info(f"[Web Push] Deleted expired subscription {sub.id}")
            except Exception as e:
                logger.error(f"[Web Push Error] {e}")
    except Exception as general_ex:
        logger.error(f"[Push Service Error] {general_ex}")
