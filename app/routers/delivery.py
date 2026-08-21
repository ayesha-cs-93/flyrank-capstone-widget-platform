from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Widget
from app.schemas import WidgetConfigOut

router = APIRouter(tags=["delivery"])

# The actual embeddable script. Kept intentionally small: fetch config,
# render a minimal form, POST to /api/submissions on submit.
WIDGET_JS = """
(function () {
  var script = document.currentScript;
  var widgetId = new URL(script.src).searchParams.get("id");
  var apiBase = new URL(script.src).origin;

  fetch(apiBase + "/api/widgets/" + widgetId + "/config")
    .then(function (r) { return r.json(); })
    .then(function (cfg) {
      var container = document.createElement("div");
      container.innerHTML =
        '<form id="fr-widget-form">' +
        '<h3>' + cfg.title + '</h3>' +
        (cfg.description ? '<p>' + cfg.description + '</p>' : '') +
        '<input name="name" placeholder="Name" required />' +
        '<input name="email" type="email" placeholder="Email" required />' +
        '<textarea name="message" placeholder="Message"></textarea>' +
        '<input name="honeypot" style="position:absolute;left:-9999px" tabindex="-1" autocomplete="off" />' +
        '<button type="submit">' + cfg.button_text + '</button>' +
        '</form>';
      script.parentNode.insertBefore(container, script);

      document.getElementById("fr-widget-form").addEventListener("submit", function (e) {
        e.preventDefault();
        var fd = new FormData(e.target);
        fetch(apiBase + "/api/submissions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            widget_id: widgetId,
            name: fd.get("name"),
            email: fd.get("email"),
            message: fd.get("message") || null,
            honeypot: fd.get("honeypot") || "",
          }),
        }).then(function () {
          container.innerHTML = "<p>Thanks — we got it.</p>";
        });
      });
    });
})();
"""


@router.get("/widget.js")
def get_widget_script():
    # versioned bundle: cache forever. If the script itself changes, bump the
    # filename/query in the embed snippet template (not implemented here since
    # the script logic itself is stable -- only widget CONFIG changes per-widget).
    return Response(
        content=WIDGET_JS,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/api/widgets/{widget_id}/config", response_model=WidgetConfigOut)
def get_widget_config(widget_id: str, response: Response, db: Session = Depends(get_db)):
    widget = db.query(Widget).filter(Widget.id == widget_id).first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")

    # short-lived cache: config can change (owner edits widget) but shouldn't
    # be refetched on every single page load
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["Access-Control-Allow-Origin"] = "*"

    return WidgetConfigOut(
        title=widget.title,
        description=widget.description,
        button_text=widget.button_text,
    )
