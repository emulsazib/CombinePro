"""The seven real Settings pages."""
from app.ui.views.settings_pages.agents_page import AgentsPage
from app.ui.views.settings_pages.api_page import ApiPage
from app.ui.views.settings_pages.general_page import GeneralPage
from app.ui.views.settings_pages.git_page import GitPage
from app.ui.views.settings_pages.memory_page import MemoryPage
from app.ui.views.settings_pages.models_page import ModelsPage
from app.ui.views.settings_pages.usage_page import SessionStats, UsagePage

__all__ = [
    "AgentsPage",
    "ApiPage",
    "GeneralPage",
    "GitPage",
    "MemoryPage",
    "ModelsPage",
    "SessionStats",
    "UsagePage",
]
