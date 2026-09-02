"""Unit tests for sub-agent discovery and Agent Runtime URL construction in luncher_agent."""

import logging
import os
import pytest

from app.agent import discover_sub_agent, format_agent_runtime_url


def test_format_agent_runtime_url_from_bare_id(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_ID", "my-gcp-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    url = format_agent_runtime_url("6460173422172307456")
    expected = (
        "https://us-central1-aiplatform.googleapis.com/reasoningEngines/v1"
        "/projects/my-gcp-project/locations/us-central1/reasoningEngines/6460173422172307456"
        "/api/a2a/app/.well-known/agent-card.json"
    )
    assert url == expected


def test_format_agent_runtime_url_from_resource_path() -> None:
    resource = "projects/506927979624/locations/us-central1/reasoningEngines/1102015765508259840"
    url = format_agent_runtime_url(resource)
    expected = (
        "https://us-central1-aiplatform.googleapis.com/reasoningEngines/v1"
        "/projects/506927979624/locations/us-central1/reasoningEngines/1102015765508259840"
        "/api/a2a/app/.well-known/agent-card.json"
    )
    assert url == expected


def test_format_agent_runtime_url_custom_app_name() -> None:
    url = format_agent_runtime_url(
        "12345",
        project_id="test-proj",
        location="us-east1",
        app_name="custom_app",
    )
    expected = (
        "https://us-east1-aiplatform.googleapis.com/reasoningEngines/v1"
        "/projects/test-proj/locations/us-east1/reasoningEngines/12345"
        "/api/a2a/custom_app/.well-known/agent-card.json"
    )
    assert url == expected


def test_discover_sub_agent_via_engine_id_env(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_ID", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setenv("STRATEGY_AGENT_ENGINE_ID", "6460173422172307456")

    agent = discover_sub_agent(
        agent_name="strategy_agent",
        default_local_url="http://localhost:8081/a2a/app/.well-known/agent-card.json",
        description="Strategy analyst",
    )

    expected_url = (
        "https://us-central1-aiplatform.googleapis.com/reasoningEngines/v1"
        "/projects/test-project/locations/us-central1/reasoningEngines/6460173422172307456"
        "/api/a2a/app/.well-known/agent-card.json"
    )
    assert agent._agent_card_source == expected_url


def test_discover_sub_agent_via_short_alias_engine_id(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_ID", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.delenv("STRATEGY_AGENT_ENGINE_ID", raising=False)
    monkeypatch.setenv("STRAT_AGENT_ENGINE_ID", "999888777")

    agent = discover_sub_agent(
        agent_name="strategy_agent",
        default_local_url="http://localhost:8081/a2a/app/.well-known/agent-card.json",
        description="Strategy analyst",
    )

    assert "reasoningEngines/999888777" in str(agent._agent_card_source)


def test_discover_sub_agent_via_runtime_id_resource(monkeypatch) -> None:
    resource = "projects/999/locations/europe-west1/reasoningEngines/888"
    monkeypatch.setenv("SCHEDULING_AGENT_RUNTIME_ID", resource)

    agent = discover_sub_agent(
        agent_name="scheduling_agent",
        default_local_url="http://localhost:8082/a2a/app/.well-known/agent-card.json",
        description="Scheduling coordinator",
    )

    assert agent._agent_card_source == (
        "https://europe-west1-aiplatform.googleapis.com/reasoningEngines/v1/"
        f"{resource}/api/a2a/app/.well-known/agent-card.json"
    )


def test_discover_sub_agent_via_direct_url_env(monkeypatch) -> None:
    custom_url = "https://custom-sched.run.app/a2a/app/.well-known/agent-card.json"
    monkeypatch.delenv("SCHEDULING_AGENT_ENGINE_ID", raising=False)
    monkeypatch.delenv("SCHEDULING_AGENT_RUNTIME_ID", raising=False)
    monkeypatch.delenv("SCHED_AGENT_ENGINE_ID", raising=False)
    monkeypatch.setenv("SCHEDULING_AGENT_URL", custom_url)

    agent = discover_sub_agent(
        agent_name="scheduling_agent",
        default_local_url="http://localhost:8082/a2a/app/.well-known/agent-card.json",
        description="Scheduling coordinator",
    )

    assert agent._agent_card_source == custom_url


def test_discover_sub_agent_local_fallback(monkeypatch) -> None:
    for var in [
        "STRATEGY_AGENT_ENGINE_ID",
        "STRATEGY_AGENT_RUNTIME_ID",
        "STRAT_AGENT_ENGINE_ID",
        "STRAT_ENGINE_ID",
        "STRATEGY_AGENT_URL",
        "STRAT_AGENT_URL",
        "STRAT_URL",
        "GOOGLE_CLOUD_AGENT_ENGINE_ID",
    ]:
        monkeypatch.delenv(var, raising=False)

    agent = discover_sub_agent(
        agent_name="strategy_agent",
        default_local_url="http://localhost:8081/a2a/app/.well-known/agent-card.json",
        description="Strategy analyst",
    )

    assert agent._agent_card_source == "http://localhost:8081/a2a/app/.well-known/agent-card.json"


def test_discover_sub_agent_warns_when_deployed_in_cloud_without_config(monkeypatch, caplog) -> None:
    for var in [
        "STRATEGY_AGENT_ENGINE_ID",
        "STRATEGY_AGENT_RUNTIME_ID",
        "STRAT_AGENT_ENGINE_ID",
        "STRAT_ENGINE_ID",
        "STRATEGY_AGENT_URL",
        "STRAT_AGENT_URL",
        "STRAT_URL",
    ]:
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", "orchestrator-engine-123")

    with caplog.at_level(logging.WARNING):
        agent = discover_sub_agent(
            agent_name="strategy_agent",
            default_local_url="http://localhost:8081/a2a/app/.well-known/agent-card.json",
            description="Strategy analyst",
        )

    assert agent._agent_card_source == "http://localhost:8081/a2a/app/.well-known/agent-card.json"
    assert "Running in Agent Runtime cloud container" in caplog.text
