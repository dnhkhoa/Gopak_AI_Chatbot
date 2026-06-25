from src.config import Settings
from src.llm.architecture import LLMArchitectureMode


def test_architecture_modes_are_explicit_and_default_legacy(monkeypatch):
    monkeypatch.delenv("LLM_ARCHITECTURE_MODE", raising=False)

    settings = Settings()

    assert settings.llm_architecture_mode == LLMArchitectureMode.LEGACY_SINGLE_MODEL
    assert {item.value for item in LLMArchitectureMode} == {
        "legacy_single_model",
        "split_roles_same_model",
        "dual_model",
    }
    assert settings.embedding_model_enabled is False


def test_split_role_model_config_is_available_without_changing_default(monkeypatch):
    monkeypatch.setenv("LLM_ARCHITECTURE_MODE", "split_roles_same_model")
    monkeypatch.setenv("FAST_STRUCTURED_MODEL", "router-model")
    monkeypatch.setenv("GROUNDED_COMPOSER_MODEL", "composer-model")

    settings = Settings()

    assert settings.llm_architecture_mode == LLMArchitectureMode.SPLIT_ROLES_SAME_MODEL
    assert settings.fast_structured_model == "router-model"
    assert settings.grounded_composer_model == "composer-model"
