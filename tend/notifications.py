"""Zero-token local notification worker. AI plans reminders only during user interaction."""
import time
from . import store

def notify(reminder):
    from plyer import notification
    from .branding import APP_NAME, icon_path, set_process_identity
    set_process_identity()
    message=reminder["title"]
    if reminder.get("task_title"):message+=" — "+reminder["task_title"]
    report=reminder.get("report")
    if report:message+=f" — {report['count']} activities this {report['period']}"
    if reminder.get("report_error"):message+=" — report unavailable"
    notification.notify(title="tether-chat · Attention", message=message[:220],
                        app_name=APP_NAME, app_icon=str(icon_path()), timeout=12)


def run():
    store.init()
    print("tether-chat attention worker running (no background AI calls)",flush=True)
    while True:
        for reminder in store.claim_notifications():
            try:
                notify(reminder)
            except Exception as exc:
                print("Desktop notification unavailable:",type(exc).__name__,flush=True)
        time.sleep(20)

if __name__=="__main__":run()
