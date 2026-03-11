import re

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def _safe_color(value, fallback):
    raw = str(value or '').strip()
    if re.fullmatch(r'#[0-9a-fA-F]{6}', raw):
        return raw
    return fallback


def _settings_dict(app_settings):
    return app_settings if isinstance(app_settings, dict) else {}


def _branding(client=None, app_settings=None):
    source = _settings_dict(app_settings)
    if not source and client is not None:
        source = _settings_dict(getattr(client, 'app_settings', {}))

    brand = source.get('brand') if isinstance(source.get('brand'), dict) else {}
    theme = source.get('theme') if isinstance(source.get('theme'), dict) else {}
    company = source.get('company') if isinstance(source.get('company'), dict) else {}
    email_cfg = source.get('email') if isinstance(source.get('email'), dict) else {}

    brand_name = str(
        brand.get('brand_name')
        or company.get('company_name')
        or (getattr(client, 'name', '') if client is not None else '')
        or 'HRM System'
    ).strip()
    return {
        'brand_name': brand_name or 'HRM System',
        'logo_url': str(brand.get('logo_url') or '').strip(),
        'tagline': str(brand.get('tagline') or '').strip(),
        'primary_color': _safe_color(theme.get('primary_color'), '#6c63ff'),
        'secondary_color': _safe_color(theme.get('secondary_color'), '#a78bfa'),
        'from_email': str(email_cfg.get('from_email') or getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')).strip(),
        'reply_to_email': str(email_cfg.get('reply_to_email') or '').strip(),
    }


def send_branded_email(
    *,
    subject,
    recipient_list,
    heading,
    greeting='',
    lines=None,
    cta_text='',
    cta_url='',
    closing='',
    client=None,
    app_settings=None,
    fail_silently=False,
):
    recipients = [str(r).strip() for r in (recipient_list or []) if str(r).strip()]
    if not recipients:
        return 0

    cfg = _branding(client=client, app_settings=app_settings)
    from_email = cfg['from_email'] or getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')
    reply_to = [cfg['reply_to_email']] if cfg.get('reply_to_email') else None

    body_lines = [str(x).strip() for x in (lines or []) if str(x).strip()]

    text_parts = []
    if greeting:
        text_parts.append(str(greeting).strip())
    if body_lines:
        text_parts.append('\n'.join(body_lines))
    if cta_url:
        text_parts.append(f'{cta_text or "Open Link"}: {cta_url}')
    if closing:
        text_parts.append(str(closing).strip())
    text_content = '\n\n'.join([p for p in text_parts if p])

    paragraphs_html = ''.join(f'<p style="margin:0 0 12px 0;color:#d8dcf0;line-height:1.6;">{line}</p>' for line in body_lines)
    logo_html = (
        f'<img src="{cfg["logo_url"]}" alt="Logo" style="width:44px;height:44px;border-radius:10px;object-fit:cover;border:1px solid rgba(255,255,255,0.15);">'
        if cfg['logo_url']
        else ''
    )
    cta_html = (
        f'<a href="{cta_url}" style="display:inline-block;margin-top:10px;padding:11px 16px;border-radius:10px;text-decoration:none;color:#ffffff;'
        f'background:linear-gradient(135deg,{cfg["primary_color"]} 0%,{cfg["secondary_color"]} 100%);font-weight:700;">{cta_text or "Open Link"}</a>'
        if cta_url
        else ''
    )
    link_fallback_html = (
        f'<p style="margin:10px 0 0 0;color:#9aa3c7;font-size:13px;">If button is not working, use this link:<br>'
        f'<a href="{cta_url}" style="color:{cfg["secondary_color"]};word-break:break-all;">{cta_url}</a></p>'
        if cta_url
        else ''
    )
    greeting_html = f'<p style="margin:0 0 12px 0;color:#d8dcf0;line-height:1.6;">{greeting}</p>' if greeting else ''
    closing_html = f'<p style="margin:14px 0 0 0;color:#9aa3c7;line-height:1.6;">{closing}</p>' if closing else ''

    html_content = f"""
<!doctype html>
<html>
<body style="margin:0;padding:20px;background:#0b1020;font-family:Segoe UI,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;margin:0 auto;border:1px solid rgba(255,255,255,0.12);border-radius:14px;background:#11172b;overflow:hidden;">
    <tr>
      <td style="padding:16px 20px;border-bottom:1px solid rgba(255,255,255,0.09);">
        <table role="presentation" width="100%"><tr>
          <td style="vertical-align:middle;">{logo_html}</td>
          <td style="vertical-align:middle;padding-left:12px;">
            <div style="color:#ffffff;font-size:18px;font-weight:700;">{cfg['brand_name']}</div>
            <div style="color:#9aa3c7;font-size:12px;">{cfg['tagline'] or 'HR Management Platform'}</div>
          </td>
        </tr></table>
      </td>
    </tr>
    <tr>
      <td style="padding:22px 20px;">
        <h2 style="margin:0 0 14px 0;color:#ffffff;font-size:22px;">{heading}</h2>
        {greeting_html}
        {paragraphs_html}
        {cta_html}
        {link_fallback_html}
        {closing_html}
      </td>
    </tr>
  </table>
</body>
</html>
""".strip()

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email,
        to=recipients,
        reply_to=reply_to,
    )
    email.attach_alternative(html_content, 'text/html')
    email.send(fail_silently=fail_silently)
    return 1
