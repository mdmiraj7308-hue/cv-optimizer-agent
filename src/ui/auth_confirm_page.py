"""HTML welcome page shown after Supabase email verification."""

from __future__ import annotations


def build_auth_confirm_html(*, streamlit_url: str) -> str:
    """Return a self-contained HTML page that reads Supabase hash/query params."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Job Finder — Email Verification</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: Arial, Helvetica, sans-serif;
      background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0f172a 100%);
      color: #e2e8f0;
      padding: 24px;
    }}
    .card {{
      max-width: 520px;
      width: 100%;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 40px 36px;
      text-align: center;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
    }}
    .icon {{ font-size: 3rem; margin-bottom: 12px; }}
    h1 {{ font-size: 1.6rem; margin: 0 0 8px; color: #f8fafc; }}
    p {{ color: #94a3b8; line-height: 1.6; margin: 0 0 20px; }}
    .btn {{
      display: inline-block;
      background: #3b82f6;
      color: #fff;
      text-decoration: none;
      padding: 12px 28px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 1rem;
      transition: background 0.2s;
    }}
    .btn:hover {{ background: #2563eb; }}
    .error-box {{
      background: #450a0a;
      border: 1px solid #7f1d1d;
      border-radius: 8px;
      padding: 14px 18px;
      margin-bottom: 20px;
      color: #fca5a5;
      font-size: 0.9rem;
      text-align: left;
    }}
    .steps {{
      text-align: left;
      background: #0f172a;
      border-radius: 8px;
      padding: 16px 20px;
      margin: 16px 0 24px;
    }}
    .steps li {{ margin-bottom: 6px; color: #cbd5e1; }}
    .hidden {{ display: none; }}
  </style>
</head>
<body>
  <div class="card">
    <div id="loading">
      <div class="icon">⏳</div>
      <h1>Verifying your email…</h1>
      <p>Please wait a moment.</p>
    </div>

    <div id="success" class="hidden">
      <div class="icon">✅</div>
      <h1>Thank you for verifying!</h1>
      <p>Welcome to <strong>Job Finder</strong> — your AI career assistant.</p>
      <div class="steps">
        <p style="margin-top:0;color:#e2e8f0;font-weight:600;">Get started:</p>
        <ol>
          <li>Open the app and <strong>Sign In</strong> with your email and password.</li>
          <li>Upload your CV and set your job preferences.</li>
          <li>Click <strong>Run Now</strong> to find matching jobs.</li>
        </ol>
      </div>
      <a class="btn" href="{streamlit_url}">Open Job Finder App →</a>
    </div>

    <div id="error" class="hidden">
      <div class="icon">⚠️</div>
      <h1>Verification issue</h1>
      <div class="error-box" id="error-detail"></div>
      <p id="error-hint"></p>
      <a class="btn" href="{streamlit_url}">Go to Sign In →</a>
    </div>
  </div>

  <script>
    const streamlitUrl = {streamlit_url!r};

    function parseParams() {{
      const hash = new URLSearchParams(window.location.hash.slice(1));
      const query = new URLSearchParams(window.location.search);
      const get = (k) => hash.get(k) || query.get(k);
      return {{
        accessToken: get("access_token"),
        error: get("error"),
        errorCode: get("error_code"),
        errorDescription: get("error_description"),
        type: get("type"),
      }};
    }}

    function show(id) {{
      ["loading", "success", "error"].forEach((s) => {{
        document.getElementById(s).classList.toggle("hidden", s !== id);
      }});
    }}

    const p = parseParams();

    if (p.accessToken) {{
      show("success");
    }} else if (p.error) {{
      show("error");
      const desc = (p.errorDescription || p.error || "Verification failed.")
        .replace(/\\+/g, " ");
      document.getElementById("error-detail").textContent = desc;

      let hint = "Return to the app and try signing in. If your email is not confirmed yet, sign up again to receive a new link.";
      if (p.errorCode === "otp_expired") {{
        hint = "This confirmation link has expired. Go back to the app, open Sign Up, and create your account again to receive a fresh verification email. Then click the new link promptly.";
      }} else if (p.errorCode === "access_denied") {{
        hint = "The verification link could not be accepted. Request a new confirmation email from the Sign Up tab.";
      }}
      document.getElementById("error-hint").textContent = hint;
    }} else {{
      show("success");
      document.querySelector("#success h1").textContent = "Welcome to Job Finder!";
      document.querySelector("#success p").textContent =
        "If you have already confirmed your email, sign in below to get started.";
    }}
  </script>
</body>
</html>"""
