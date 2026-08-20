import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class GalleryFrontendRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = (ROOT / "pages" / "shoubanhua" / "app.js").read_text(
            encoding="utf-8"
        )
        cls.html_source = (ROOT / "pages" / "shoubanhua" / "index.html").read_text(
            encoding="utf-8"
        )
        cls.style_source = (ROOT / "pages" / "shoubanhua" / "style.css").read_text(
            encoding="utf-8"
        )

    def test_overview_uses_status_capacity(self):
        self.assertIn("Number(data.max_gb)", self.app_source)
        self.assertNotIn("state.config?.image_storage_max_gb || 5.0", self.app_source)

    def test_legacy_group_origin_is_not_rendered_as_private_chat(self):
        self.assertIn("GroupMessage:(.+)", self.app_source)
        self.assertIn("legacyGroupMatch", self.app_source)
        self.assertIn("未知用户", self.app_source)

    def test_initial_storage_placeholder_does_not_claim_five_gb(self):
        self.assertIn("存储占用: 加载中...", self.html_source)
        self.assertNotIn("存储占用: 0 MB / 5 GB", self.html_source)

    def test_detail_inspector_exposes_full_gallery_metadata(self):
        for element_id in (
            "lightboxPrompt",
            "lightboxGenerationMeta",
            "lightboxFileMeta",
            "lightboxCopyPromptBtn",
            "lightboxDeleteBtn",
        ):
            self.assertIn(f'id="{element_id}"', self.html_source)
        for field in ("item.prompt", "item.model", "item.filename", "item.id"):
            self.assertIn(field, self.app_source)

    def test_preview_keeps_progressive_raw_image_loading(self):
        self.assertIn("currentLightboxReqId", self.app_source)
        self.assertIn("apiGet('gallery/raw'", self.app_source)
        self.assertIn("const fullImg = new Image()", self.app_source)
        self.assertIn("img.style.filter = item.url ? 'blur(4px)' : 'none'", self.app_source)
        self.assertIn("requestId !== currentLightboxReqId", self.app_source)

    def test_persona_preview_uses_shared_inspector(self):
        self.assertIn("kind: 'persona'", self.app_source)
        self.assertIn("openImagePreview", self.app_source)
        self.assertIn("mediaButton.addEventListener('click'", self.app_source)
        self.assertNotIn("lightboxImage", self.app_source)
        self.assertNotIn("lightboxMeta", self.app_source)
        self.assertNotIn('onclick="window.viewPersonaPhoto', self.app_source)

    def test_prompt_is_full_text_and_static_assets_share_version(self):
        self.assertIn("white-space: pre-wrap", self.style_source)
        self.assertIn("overflow-wrap: anywhere", self.style_source)
        self.assertIn('./style.css?v=20260820-3', self.html_source)
        self.assertIn('./app.js?v=20260820-3', self.html_source)

    def test_detail_dialog_supports_keyboard_and_focus(self):
        self.assertIn('role="dialog"', self.html_source)
        self.assertIn("closeImagePreview", self.app_source)
        self.assertIn("e.key === 'Escape'", self.app_source)
        self.assertIn("getLightboxFocusableElements", self.app_source)
        self.assertIn("lightboxReturnFocus", self.app_source)

    def test_gallery_click_passes_structured_item(self):
        self.assertIn("{ kind: 'gallery', item: previewItem }", self.app_source)
        self.assertNotIn('onclick="window.previewImage(', self.app_source)


if __name__ == "__main__":
    unittest.main()
