import base64
import unittest

from gmail_workflow import classify_message, extract_message_text, build_triage_item


def encoded(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


class GmailWorkflowTests(unittest.TestCase):
    def test_extracts_plain_text(self):
        message = {"payload": {"mimeType": "text/plain", "body": {"data": encoded("Olá, vamos agendar uma entrevista?")}}}
        self.assertIn("entrevista", extract_message_text(message))

    def test_extracts_nested_plain_text_before_html(self):
        message = {"payload": {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/plain", "body": {"data": encoded("Texto simples")}},
            {"mimeType": "text/html", "body": {"data": encoded("<p>HTML</p>")}},
        ]}}
        self.assertEqual(extract_message_text(message), "Texto simples")

    def test_classifies_offer_as_high_priority_and_needs_review(self):
        result = classify_message("Proposta salarial", "RH", "Segue a oferta de emprego")
        self.assertEqual(result["priority"], "alta")
        self.assertTrue(result["requires_human_review"])
        self.assertFalse(result["external_action_allowed"])

    def test_builds_item_from_headers_and_body(self):
        message = {"id": "m1", "threadId": "t1", "snippet": "snippet", "payload": {
            "headers": [{"name": "From", "value": "RH <rh@example.com>"}, {"name": "Subject", "value": "Entrevista"}],
            "mimeType": "text/plain", "body": {"data": encoded("Podemos marcar uma entrevista?")},
        }}
        item = build_triage_item(message, "SG")
        self.assertEqual(item["account"], "SG")
        self.assertIn("entrevista", item["triage"]["categories"])

    def test_google_account_security_notice_is_not_recruitment(self):
        result = classify_message(
            "Você compartilhou alguns dados da sua Conta do Google com Spotify",
            "Google <noreply-accounts@google.com>",
            "Você está recebendo este e-mail porque usou Fazer Login com o Google.",
        )
        self.assertEqual(result["categories"], ["seguranca_conta"])
        self.assertEqual(result["priority"], "alta")

    def test_render_cron_failure_is_operational_alert(self):
        result = classify_message(
            "Cron job failure detected on automacao-murici-scheduler",
            "Render <no-reply@render.com>",
            "Reason: Exited with status 22. The most recent cron job run failed.",
        )
        self.assertEqual(result["categories"], ["alerta_operacional"])
        self.assertEqual(result["priority"], "alta")

    def test_one_time_login_code_is_redacted_from_triage_output(self):
        message = {"id": "m2", "threadId": "t2", "snippet": "123456 – Seu código de login do Spotify", "payload": {
            "headers": [
                {"name": "From", "value": "Spotify <no-reply@alerts.spotify.com>"},
                {"name": "Subject", "value": "Seu código de login 123456"},
            ],
            "mimeType": "text/plain",
            "body": {"data": encoded("Insira este código para continuar: 123456")},
        }}
        item = build_triage_item(message, "Drive1")
        self.assertNotIn("123456", item["body_text"])
        self.assertNotIn("123456", item["snippet"])
        self.assertNotIn("123456", item["subject"])
        self.assertEqual(item["triage"]["categories"], ["seguranca_conta"])

    def test_spotify_new_login_is_security_alert(self):
        result = classify_message("Novo login no Spotify", "Spotify <no-reply@spotify.com>", "Um novo login foi detectado.")
        self.assertEqual(result["categories"], ["seguranca_conta"])
        self.assertEqual(result["priority"], "alta")

    def test_indeed_job_digest_is_vacancy_alert_not_recruiter_contact(self):
        result = classify_message("21 novas vagas para você", "Indeed <alert@indeed.com>", "Vagas que combinam com seu perfil.")
        self.assertEqual(result["categories"], ["alerta_vaga"])
        self.assertEqual(result["priority"], "media")

    def test_marketing_case_word_does_not_trigger_selection_test(self):
        result = classify_message("A better roller – What’s new in October", "Metricool", "New product features and updates.")
        self.assertNotIn("teste_seletivo", result["categories"])

    def test_linkedin_connection_notification_is_not_document_priority(self):
        result = classify_message("Lucas aceitou seu convite", "LinkedIn", "Agora vocês são conexões.")
        self.assertEqual(result["categories"], ["nao_classificado"])
        self.assertEqual(result["priority"], "normal")

    def test_generic_document_keyword_does_not_create_high_priority(self):
        result = classify_message("Pasta compartilhada com você", "Google Drive", "A pasta contém documentos.")
        self.assertEqual(result["categories"], ["documentos"])
        self.assertEqual(result["priority"], "media")


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
