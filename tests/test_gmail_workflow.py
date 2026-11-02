import base64
import unittest

from gmail_workflow import classify_message, extract_message_text, build_triage_item, summarize_triage_items, summary_only_requested


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
        result = classify_message("Proposta salarial", "RH", "Segue a oferta de emprego", account="SG")
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

    def test_short_verification_code_is_redacted_in_all_returned_text_fields(self):
        message = {"id": "m3", "threadId": "t3", "snippet": "Código de verificação: 4821", "payload": {
            "headers": [
                {"name": "From", "value": "Serviço <no-reply@example.com>"},
                {"name": "Subject", "value": "Seu código de verificação 4821"},
            ],
            "mimeType": "text/plain",
            "body": {"data": encoded("Use o código de segurança 4821 para continuar.")},
        }}
        item = build_triage_item(message, "Drive2")
        self.assertNotIn("4821", item["body_text"])
        self.assertNotIn("4821", item["snippet"])
        self.assertNotIn("4821", item["subject"])

    def test_spotify_new_login_is_security_alert(self):
        result = classify_message("Novo login no Spotify", "Spotify <no-reply@spotify.com>", "Um novo login foi detectado.")
        self.assertEqual(result["categories"], ["seguranca_conta"])
        self.assertEqual(result["priority"], "alta")

    def test_indeed_job_digest_is_vacancy_alert_not_recruiter_contact(self):
        result = classify_message("21 novas vagas para você", "Indeed <alert@indeed.com>", "Vagas que combinam com seu perfil.", account="SG")
        self.assertEqual(result["categories"], ["alerta_vaga"])
        self.assertEqual(result["priority"], "media")

    def test_marketing_case_word_does_not_trigger_selection_test(self):
        result = classify_message("A better roller – What’s new in October", "Metricool", "New product features and updates.")
        self.assertNotIn("teste_seletivo", result["categories"])

    def test_linkedin_connection_notification_is_not_document_priority(self):
        result = classify_message("Lucas aceitou seu convite", "LinkedIn", "Agora vocês são conexões.")
        self.assertEqual(result["categories"], ["nao_classificado"])
        self.assertEqual(result["priority"], "normal")

    def test_drive2_interview_word_is_not_classified_as_recruitment(self):
        result = classify_message(
            "Entrevista sobre atualização de produto",
            "Notificação de serviço",
            "Convite para uma entrevista sobre novidades da plataforma.",
            account="Drive2",
        )
        self.assertEqual(result["categories"], ["nao_classificado"])
        self.assertEqual(result["priority"], "normal")

    def test_drive2_job_process_terms_are_not_classified_as_recruitment(self):
        result = classify_message(
            "Próxima etapa do processo seletivo",
            "Remetente genérico",
            "Agendar entrevista e realizar teste técnico.",
            account="Drive2",
        )
        self.assertEqual(result["categories"], ["nao_classificado"])
        self.assertEqual(result["priority"], "normal")

    def test_pandape_online_tests_subject_alone_is_classified_as_selection_test(self):
        result = classify_message(
            "Processo Seletivo | Aprovação Testes Online",
            "PandaPé <no-reply@pandape.com.br>",
            "",
            account="SG",
        )
        self.assertIn("teste_seletivo", result["categories"])
        self.assertEqual(result["priority"], "alta")

    def test_pandape_subject_matches_without_sender_or_body_context(self):
        result = classify_message(
            "Processo Seletivo | Aprovação Testes Online",
            "",
            "",
            account="SG",
        )
        self.assertEqual(result["categories"], ["teste_seletivo"])
        self.assertEqual(result["priority"], "alta")

    def test_drive1_professional_mailbox_classifies_interview(self):
        result = classify_message(
            "Convite para entrevista",
            "Recrutamento",
            "Podemos agendar uma conversa?",
            account="Drive1",
        )
        self.assertIn("entrevista", result["categories"])
        self.assertEqual(result["priority"], "alta")

    def test_drive1_indeed_digest_is_vacancy_alert(self):
        result = classify_message(
            "21 novas vagas para você",
            "Indeed <alert@indeed.com>",
            "Vagas que combinam com seu perfil.",
            account="Drive1",
        )
        self.assertEqual(result["categories"], ["alerta_vaga"])

    def test_sg_mailbox_still_classifies_interview(self):
        result = classify_message(
            "Convite para entrevista",
            "Recrutamento",
            "Podemos agendar uma conversa?",
            account="SG",
        )
        self.assertIn("entrevista", result["categories"])
        self.assertEqual(result["priority"], "alta")

    def test_generic_congratulations_do_not_trigger_next_stage(self):
        result = classify_message(
            "Parabéns pela sua compra",
            "Loja Online",
            "Seu pedido foi confirmado.",
            account="SG",
        )
        self.assertEqual(result["categories"], ["nao_classificado"])
        self.assertEqual(result["priority"], "normal")

    def test_explicit_next_stage_notice_is_classified(self):
        result = classify_message(
            "Processo seletivo – próxima etapa",
            "Equipe de Recrutamento",
            "Convidamos você para a próxima etapa do processo.",
            account="SG",
        )
        self.assertIn("proxima_etapa", result["categories"])
        self.assertEqual(result["priority"], "alta")

    def test_generic_document_keyword_does_not_create_high_priority(self):
        result = classify_message("Pasta compartilhada com você", "Google Drive", "A pasta contém documentos.")
        self.assertEqual(result["categories"], ["documentos"])
        self.assertEqual(result["priority"], "media")


    def test_summary_only_is_the_default_for_privacy(self):
        self.assertTrue(summary_only_requested())
        self.assertTrue(summary_only_requested(None))

    def test_summary_only_accepts_explicit_true_values(self):
        for value in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(value=value):
                self.assertTrue(summary_only_requested(value))

    def test_full_message_details_require_explicit_false_opt_in(self):
        for value in ("0", "false", "no", "off", ""):
            with self.subTest(value=value):
                self.assertFalse(summary_only_requested(value))

    def test_unclassified_summary_exposes_only_aggregate_diagnostic_signals(self):
        items = [
            {"subject": "Confirme seu e-mail", "from": "Serviço", "snippet": "Ative sua conta", "body_text": "Bem-vindo", "triage": {"categories": ["nao_classificado"], "priority": "normal"}},
            {"subject": "Newsletter de outubro", "from": "Marca", "snippet": "Ofertas exclusivas", "body_text": "Unsubscribe", "triage": {"categories": ["nao_classificado"], "priority": "normal"}},
            {"subject": "Mensagem privada não deve aparecer", "body_text": "Texto confidencial", "triage": {"categories": ["nao_classificado"], "priority": "normal"}},
        ]
        summary = summarize_triage_items(items)
        self.assertEqual(summary["unclassified_signals"], {
            "cadastro_validacao": 1,
            "marketing_newsletter": 1,
        })
        serialized = str(summary)
        self.assertNotIn("Mensagem privada", serialized)
        self.assertNotIn("Texto confidencial", serialized)
        self.assertNotIn("Confirme seu e-mail", serialized)

    def test_triage_summary_contains_only_aggregate_classification_counts(self):
        items = [
            {"subject": "PRIVATE SUBJECT", "triage": {"categories": ["entrevista", "contato_recrutador"], "priority": "alta"}},
            {"subject": "ANOTHER PRIVATE SUBJECT", "triage": {"categories": ["alerta_vaga"], "priority": "media"}},
            {"triage": {"categories": ["entrevista"], "priority": "alta"}},
        ]
        summary = summarize_triage_items(items)
        self.assertEqual(summary, {
            "total": 3,
            "categories": {"alerta_vaga": 1, "contato_recrutador": 1, "entrevista": 2},
            "priorities": {"alta": 2, "media": 1},
        })
        self.assertNotIn("PRIVATE SUBJECT", str(summary))


if __name__ == "__main__":
    unittest.main()
