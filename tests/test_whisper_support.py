from __future__ import annotations

import tempfile
import unittest
import json
from email import message_from_string
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

from tools.audio_capture import capture_device_audio
from tools.link_title_generator import load_link_titles, random_link_title, save_link_titles
from tools.name_email_generator import random_first_name, random_name_profile, random_training_username, random_user
from tools.runtime_variables import RuntimeVariables
from tools.zoho_code_reader import _message_addresses
from tools.whisper_engine import extract_verification_code
from app import Action, Adb, DEFAULT_PANELS, MacroApp


class WhisperCodeTests(unittest.TestCase):
    def test_default_panels_have_stable_storage_ids(self) -> None:
        panels = {panel["name"]: panel["id"] for panel in DEFAULT_PANELS}
        self.assertEqual(panels["Treinar"], "treinar")

    def test_legacy_media_send_gets_processing_before_upload(self) -> None:
        groups = MacroApp._groups_from_data({"groups": [{"name": "Grupo", "actions": [
            {"kind": "random_user_files", "file_paths": ["C:/midia.jpg"]},
        ]}]})
        self.assertEqual([action.kind for action in groups[0]["actions"]], ["random_user_files"])

    def test_normal_media_sequential_choice_wraps_without_touching_source_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            first, second = folder / "01.jpg", folder / "02.jpg"
            first.write_bytes(b"a"); second.write_bytes(b"b")
            chosen, next_index = MacroApp._select_normal_media([second, first], "sequential", 0)
            self.assertEqual(chosen, first)
            self.assertEqual(next_index, 1)
            chosen, next_index = MacroApp._select_normal_media([first, second], "sequential", next_index)
            self.assertEqual(chosen, second)
            self.assertEqual(next_index, 0)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_text_typing_quotes_hashtags_for_adb_shell(self) -> None:
        adb = Mock()
        MacroApp._type_link_title(None, adb, "#teste #iggen")
        self.assertEqual(adb.command.call_args.args, ("shell", "input", "text", "'#teste%s#iggen'"))

    def test_link_titles_are_saved_and_selected_from_their_own_list(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "titulos_links.txt"
            self.assertEqual(save_link_titles(path, ["Primeiro", "", "Segundo"]), ["Primeiro", "Segundo"])
            self.assertEqual(load_link_titles(path), ["Primeiro", "Segundo"])
            self.assertIn(random_link_title(path), {"Primeiro", "Segundo"})

    def test_preview_click_maps_image_edges_to_screen_edges(self) -> None:
        self.assertEqual(MacroApp._preview_point_to_screen(0, 0, 190, 350, 1080, 2408), (0, 0))
        self.assertEqual(MacroApp._preview_point_to_screen(189, 349, 190, 350, 1080, 2408), (1079, 2407))

    def test_instagram_code_reader_uses_the_real_message_recipient(self) -> None:
        message = message_from_string("To: Heloisa <heloisa@example.com>\nDelivered-To: heloisa@example.com\n\nCódigo")
        self.assertIn("heloisa@example.com", _message_addresses(message))

    def test_preview_uses_the_macro_screen_for_all_new_coordinates(self) -> None:
        action = Action(kind="tap", x=533, y=1566)
        self.assertEqual(MacroApp._action_coordinate_screen(action, (720, 1640), ("1080", "1920")), (720, 1640))

    def test_loading_normalizes_old_preview_coordinates_outside_macro_screen(self) -> None:
        groups = MacroApp._groups_from_data({
            "screen": [720, 1640],
            "device": {"raw_size": ["1080", "1920"]},
            "groups": [{"name": "Grupo", "actions": [{"kind": "tap", "x": 959, "y": 1875}]}],
        })
        action = groups[0]["actions"][0]
        self.assertEqual((action.x, action.y), (639, 1601))

    def test_execution_scales_saved_coordinates_to_the_connected_screen(self) -> None:
        actions = [Action(kind="swipe", x=540, y=1204, x2=810, y2=1806)]
        scaled = MacroApp._scale_actions_to_target_screen(actions, (1080, 2408), ("1080", "2408"), (720, 1640))
        self.assertEqual((scaled[0].x, scaled[0].y, scaled[0].x2, scaled[0].y2), (360, 820, 540, 1230))
        self.assertEqual((actions[0].x, actions[0].y), (540, 1204))

    def test_xml_search_accepts_variable_text_between_fragments(self) -> None:
        xml = '<hierarchy><node text="Story de ajoyceolv5, 1 de 16, Não visualizado." bounds="[10,20][30,40]" /></hierarchy>'
        self.assertEqual(MacroApp._xml_logic_bounds(xml, "Story de 1 de 16"), (20, 30))
        self.assertFalse(MacroApp._xml_query_matches("Story de ingridsohh, 0 de 16, Não visualizado.", "Story de 1 de 16"))

    def test_nav_xml_queries_share_one_snapshot(self) -> None:
        xml = ('<hierarchy><node text="Curtir" bounds="[10,20][30,40]" />'
               '<node text="Patrocinado" bounds="[50,60][70,80]" /></hierarchy>')
        self.assertEqual(
            MacroApp._xml_logic_bounds_many(xml, ["Curtir", "Patrocinado", "Sugest\u00f5es"]),
            [(20, 30), (60, 70), None],
        )

    def test_xml_search_includes_non_text_attributes(self) -> None:
        resource_id = "com.instagram.android:id/swipeable_tab_view_pager"
        searchable = MacroApp._xml_searchable({"resource-id": resource_id, "scrollable": "true"})
        self.assertTrue(MacroApp._xml_query_matches(searchable, "swipeable"))
        self.assertTrue(MacroApp._xml_query_matches(searchable, resource_id))
        self.assertTrue(MacroApp._xml_query_matches(searchable, "scrollable"))

    def test_xml_search_accepts_partial_text_and_resource_id(self) -> None:
        self.assertTrue(MacroApp._xml_query_matches("dorinhasant2s android widget button", "dorinha"))
        self.assertTrue(MacroApp._xml_query_matches("com instagram android id reels tray container", "androi"))

    def test_xml_search_combines_text_with_class_address_in_any_attribute_order(self) -> None:
        searchable = MacroApp._xml_searchable({"class": "android.widget.Button", "text": "Concordo"})
        self.assertTrue(MacroApp._xml_query_matches(searchable, "concordo .button"))
        self.assertFalse(MacroApp._xml_query_matches(searchable, "concordo .imageview"))

    def test_xml_blocked_values_accept_comma_separated_items(self) -> None:
        self.assertTrue(MacroApp._xml_has_blocked_text("Story patrocinado android widget", "Patrocinado, Sugestões"))
        self.assertTrue(MacroApp._xml_has_blocked_text("Story sugestões", "Patrocinado, Sugestões"))
        self.assertFalse(MacroApp._xml_has_blocked_text("Story normal", "Patrocinado, Sugestões"))

    def test_xml_capture_recovers_after_uiautomator_is_killed(self) -> None:
        adb = Adb()
        adb.command = Mock(side_effect=[
            RuntimeError("ADB falhou: Killed"),  # primeira captura
            "",                                  # segunda tentativa sem XML
            "",                                # limpeza do processo preso
            '<hierarchy><node bounds="[0,0][1,1]" /></hierarchy>',  # dump direto após limpar
        ])
        with patch("app.time.sleep"):
            self.assertIn("hierarchy", adb.ui_xml(timeout=2))
        self.assertEqual(adb.command.call_count, 4)

    def test_nav_r_xml_queries_keep_each_non_empty_line_when_saved(self) -> None:
        edited = "Sugestões\nAnúncio\nPatrocinado\n sugestões \n\n"
        self.assertEqual(
            MacroApp._normalise_xml_query_lines(edited),
            ["Sugestões", "Anúncio", "Patrocinado"],
        )
        self.assertEqual(
            MacroApp._normalise_xml_query_lines(["Sugestões", "Anúncio", "Patrocinado"]),
            ["Sugestões", "Anúncio", "Patrocinado"],
        )

    def test_exact_xml_selector_does_not_choose_the_first_similar_element(self) -> None:
        xml = (
            '<hierarchy>'
            '<node text="Reels" resource-id="first" class="android.widget.FrameLayout" bounds="[0,0][50,50]" />'
            '<node text="Reels" resource-id="wanted" class="android.widget.FrameLayout" bounds="[100,200][300,400]" />'
            '</hierarchy>'
        )
        action = Action("xml_tap", selector_type="exact_xml", selector_value=json.dumps({
            "resource-id": "wanted", "text": "Reels", "class": "android.widget.FrameLayout", "bounds": "[100,200][300,400]",
        }))
        self.assertEqual(MacroApp._xml_bounds(xml, action), (200, 300))
        self.assertEqual(MacroApp._xml_rect(xml, action), (100, 200, 300, 400))

    def test_xml_rect_uses_the_same_flexible_search_as_logic_groups(self) -> None:
        xml = '<hierarchy><node text="Story de pessoa, 1 de 16" bounds="[10,20][310,420]" /></hierarchy>'
        action = Action("xml_logic", selector_value="Story de 1 de 16")
        self.assertEqual(MacroApp._xml_rect(xml, action), (10, 20, 310, 420))

    def test_nav_rc_extracts_text_and_uses_date_in_same_container(self) -> None:
        xml = (
            '<hierarchy><node class="comment" bounds="[0,0][500,200]">'
            '<node text="pessoa" bounds="[10,10][100,40]" />'
            '<node text="31 de julho" bounds="[110,10][220,40]" />'
            '<node text="pessoa disse Atende aí, Renner" bounds="[10,50][400,100]" />'
            '</node></hierarchy>'
        )
        self.assertEqual(MacroApp._extract_nav_rc_text(xml, "disse", 2, datetime(2026, 8, 2)),
                         ("Atende aí, Renner", "31 de julho"))
        self.assertIsNone(MacroApp._extract_nav_rc_text(xml, "disse", 1, datetime(2026, 8, 2)))

    def test_nav_rc_accepts_relative_hours_within_24_hours(self) -> None:
        xml = (
            '<hierarchy><node class="comment">'
            '<node text="Há 3 horas" bounds="[100,10][200,40]" />'
            '<node text="pessoa disse Quero" bounds="[10,50][300,90]" />'
            '</node></hierarchy>'
        )
        self.assertEqual(MacroApp._extract_nav_rc_text(xml, "disse", 0, datetime(2026, 8, 2)),
                         ("Quero", "Há 3 horas"))

    def test_nav_rc_reads_comment_count_from_accessibility_text(self) -> None:
        xml = '<hierarchy><node text="" content-desc="O número de comentários é 1.234. Ver comentários" /></hierarchy>'
        self.assertEqual(MacroApp._nav_rc_comment_count(xml), 1234)

    def test_random_name_uses_the_local_list(self) -> None:
        names = {line.strip() for line in (Path(__file__).resolve().parent.parent / "data" / "listas_nomes" / "usuariosAleatorios.txt").read_text(encoding="utf-8").splitlines() if line.strip()}
        self.assertTrue(names)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            legacy = directory / "usuariosAleatorios.txt"
            data = directory / "usuariosAleatorios.json"
            legacy.write_text("\n".join(names), encoding="utf-8")
            with patch("tools.name_email_generator.RANDOM_USERS_FILE", legacy), \
                 patch("tools.name_email_generator.RANDOM_USERS_DATA_FILE", data):
                self.assertIn(random_first_name(), names)

    def test_random_name_allows_a_list_larger_than_500_entries(self) -> None:
        names = [f"Nome {index}" for index in range(501)]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            legacy = directory / "usuariosAleatorios.txt"
            data = directory / "usuariosAleatorios.json"
            legacy.write_text("\n".join(names), encoding="utf-8")
            with patch("tools.name_email_generator.RANDOM_USERS_FILE", legacy), \
                 patch("tools.name_email_generator.RANDOM_USERS_DATA_FILE", data):
                self.assertIn(random_first_name(), names)

    def test_random_user_keeps_link_and_files_for_later_steps(self) -> None:
        user = {"nome": "Ana", "link": "https://example.com/ana", "arquivos": ["C:/arquivos/ana.pdf"]}
        with patch("tools.name_email_generator.load_random_users", return_value=[user]):
            self.assertEqual(random_user(), user)

    def test_name_profile_is_available_for_the_email_flow(self) -> None:
        profile = {"nome": "Ana", "link": "https://example.com/ana", "arquivos": ["C:/arquivos/ana.pdf"]}
        with patch("tools.name_email_generator.load_name_profiles", return_value=[profile]):
            self.assertEqual(random_name_profile(), profile)

    def test_training_user_uses_a_separate_short_list(self) -> None:
        usernames = ["saassy_g", "akiiraoficial"]
        with patch("tools.name_email_generator.load_random_users", return_value=[{"nome": name, "link": "", "arquivos": []} for name in usernames]):
            self.assertIn(random_training_username(), usernames)

    def test_extracts_alphanumeric_code(self) -> None:
        self.assertEqual(extract_verification_code("The verification code is A7B92K"), "A7B92K")

    def test_extracts_spoken_characters(self) -> None:
        self.assertEqual(
            extract_verification_code("Your verification code is A seven B nine two K."),
            "A7B92K",
        )

    def test_runtime_is_isolated_by_serial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = RuntimeVariables("SERIAL_001", temporary)
            second = RuntimeVariables("SERIAL_002", temporary)
            first.set("WHISPER_CODE", "A7B92K")
            second.set("WHISPER_CODE", "981204")
            self.assertEqual(first.require("WHISPER_CODE"), "A7B92K")
            self.assertEqual(second.require("WHISPER_CODE"), "981204")
            self.assertNotEqual(first.directory, second.directory)

    def test_new_whisper_capture_removes_stale_code_before_recording(self) -> None:
        """Uma nova escuta não pode reutilizar um código da tentativa anterior."""
        with tempfile.TemporaryDirectory() as temporary:
            variables = RuntimeVariables("SERIAL_001", temporary)
            variables.set("WHISPER_CODE", "701621")
            variables.remove("WHISPER_CODE")
            with self.assertRaises(RuntimeError):
                variables.require("WHISPER_CODE")
            variables.set("WHISPER_CODE", "981204")
            self.assertEqual(variables.require("WHISPER_CODE"), "981204")

    def test_capture_uses_device_runtime_directory(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str], timeout: float, stop_event=None):
            commands.append(command)
            output = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--record="))) \
                if any(arg.startswith("--record=") for arg in command) else Path(command[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"test")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scrcpy = root / "scrcpy.exe"
            ffmpeg = root / "ffmpeg.exe"
            scrcpy.write_bytes(b"")
            ffmpeg.write_bytes(b"")
            with patch("tools.audio_capture.find_scrcpy", return_value=scrcpy), \
                 patch("tools.audio_capture.find_ffmpeg", return_value=ffmpeg), \
                 patch("tools.audio_capture._run_process", side_effect=fake_run):
                files = capture_device_audio("SERIAL_001", root, root / "runtime", duration_s=10)

            self.assertEqual(files.directory, root / "runtime" / "SERIAL_001")
            self.assertIn("SERIAL_001", commands[0])
            self.assertIn("--audio-source=output", commands[0])
            self.assertIn("--audio-codec=aac", commands[0])
            self.assertEqual(files.wav.parent, files.m4a.parent)


if __name__ == "__main__":
    unittest.main()
