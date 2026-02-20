"""Envoi d'email de notification avec le PDF en pièce jointe via Gmail SMTP."""

import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587
MAX_ATTACHMENT_MB = 20


def send_book_email(
    pdf_path: str,
    book_title: str,
    child_name: str,
    recipient_email: str,
) -> tuple[bool, str]:
    """
    Envoie le PDF du livre par email via Gmail.

    Requiert dans .env :
        GMAIL_SENDER=monlivreunique.professional@gmail.com
        GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

    Returns:
        (True, "") si succès
        (False, message_erreur) si échec
    """
    sender_email = os.getenv("GMAIL_SENDER", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    if not sender_email:
        return False, "GMAIL_SENDER manquant dans le fichier .env"
    if not app_password:
        return False, "GMAIL_APP_PASSWORD manquant dans le fichier .env"
    if not os.path.exists(pdf_path):
        return False, f"PDF introuvable : {pdf_path}"

    # Vérifier la taille du PDF
    pdf_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    attach_pdf = pdf_size_mb <= MAX_ATTACHMENT_MB

    # ── Construire le message ──────────────────────────────────────────────────
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg["Subject"] = f'Livre de {child_name} : "{book_title}" est pret !'

    if attach_pdf:
        body = (
            f"Bonjour,\n\n"
            f'Le livre personnalise "{book_title}" pour {child_name} est termine !\n\n'
            f"Vous trouverez le PDF en piece jointe ({pdf_size_mb:.0f} Mo), "
            f"pret a imprimer en 21x21cm a 300dpi.\n\n"
            f"Bonne lecture !\n"
        )
    else:
        body = (
            f"Bonjour,\n\n"
            f'Le livre personnalise "{book_title}" pour {child_name} est termine !\n\n'
            f"Le PDF fait {pdf_size_mb:.0f} Mo (trop volumineux pour une piece jointe email).\n"
            f"Rendez-vous sur http://localhost:8501 pour le telecharger depuis l'application.\n\n"
            f"Bonne lecture !\n"
        )

    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Attacher le PDF si taille acceptable
    if attach_pdf:
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        attachment = MIMEApplication(pdf_data, _subtype="pdf")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=os.path.basename(pdf_path),
        )
        msg.attach(attachment)

    # ── Envoyer via Gmail SMTP ────────────────────────────────────────────────
    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(sender_email, app_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())

        if attach_pdf:
            return True, f"Email envoye avec le PDF en piece jointe ({pdf_size_mb:.0f} Mo)"
        else:
            return True, f"Email envoye (PDF trop volumineux pour piece jointe, {pdf_size_mb:.0f} Mo)"

    except smtplib.SMTPAuthenticationError:
        return False, (
            "Erreur d'authentification Gmail. "
            "Verifiez GMAIL_APP_PASSWORD dans .env (mot de passe d'application requis, pas le mot de passe Gmail)."
        )
    except smtplib.SMTPException as e:
        return False, f"Erreur SMTP : {e}"
    except Exception as e:
        return False, f"Erreur inattendue : {e}"
