# app/odoo_projects_gateway.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .odoo_client import odoo1_client, odoo2_client

router = APIRouter(
    prefix="/api/v1/odoo/projects",
    tags=["odoo-projects"],
)

# ==========
# Pydantic схеми
# ==========


class SyncProjectFrom1To2Request(BaseModel):
    project_id_in_1: int


class SyncProjectFrom1To2Response(BaseModel):
    project_id_in_2: int


class SyncTaskFrom1To2Request(BaseModel):
    task_id_in_1: int


class SyncTaskFrom1To2Response(BaseModel):
    task_id_in_2: int


class TaskChangedIn2Request(BaseModel):
    task_id_in_2: int


class TaskChangedIn2Response(BaseModel):
    task_id_in_1: int


# ==========
# Допоміжні функції
# ==========


def _map_task_stage_by_name(source_stage, target_env) -> Optional[int]:
    """Мапає stage_id (project.task.type) за ім’ям між базами."""
    if not source_stage:
        return None

    TaskStage = target_env["project.task.type"]
    ids = TaskStage.search([("name", "=", source_stage.name)], limit=1)
    return ids[0] if ids else None


# ==========
# Синк проєктів 1 → 2
# ==========


def sync_project_from_1_to_2(project_id_in_1: int) -> int:
    """
    Читаємо project.project з Odoo 1 і створюємо/оновлюємо відповідний
    project.project в Odoo 2.

    Використовуються поля-зв’язки:
      - в Odoo 2: project.project.x_odoo1_project_id
      - в Odoo 1: project.project.x_odoo2_project_id (опційно оновлюємо)
    """
    env1 = odoo1_client.env
    env2 = odoo2_client.env

    Project1 = env1["project.project"]
    Project2 = env2["project.project"]

    proj1 = Project1.browse(project_id_in_1)
    if not proj1.exists():
        raise HTTPException(status_code=404, detail="project not found in Odoo 1")

    # шукаємо чи вже є цей проєкт в Odoo 2
    existing_ids = Project2.search([("x_odoo1_project_id", "=", project_id_in_1)], limit=1)

    vals_2 = {
        "name": proj1.name,
        "partner_id": proj1.partner_id.id or False,
        "user_id": proj1.user_id.id or False,
        "company_id": proj1.company_id.id or False,
        # поле-зв’язка
        "x_odoo1_project_id": project_id_in_1,
    }

    if existing_ids:
        project_id_in_2 = existing_ids[0]
        proj2 = Project2.browse(project_id_in_2)
        proj2.write(vals_2)
    else:
        project_id_in_2 = Project2.create(vals_2)

    # опційно — зберігаємо зворотній ID в Odoo 1
    if hasattr(proj1, "x_odoo2_project_id"):
        proj1.write({"x_odoo2_project_id": project_id_in_2})

    return project_id_in_2


# ==========
# Синк тасків 1 → 2
# ==========


def sync_task_from_1_to_2(task_id_in_1: int) -> int:
    """
    Читаємо project.task з Odoo 1 і створюємо/оновлюємо відповідний
    project.task в Odoo 2.

    Поля-зв’язки:
      - в Odoo 2: project.task.x_odoo1_task_id
      - в Odoo 1: project.task.x_odoo2_task_id (опційно оновлюємо)
    """
    env1 = odoo1_client.env
    env2 = odoo2_client.env

    Task1 = env1["project.task"]
    Task2 = env2["project.task"]

    task1 = Task1.browse(task_id_in_1)
    if not task1.exists():
        raise HTTPException(status_code=404, detail="task not found in Odoo 1")

    # гарантуємо, що відповідний проєкт є в Odoo 2
    project_id_in_2 = None
    if task1.project_id:
        project_id_in_2 = sync_project_from_1_to_2(task1.project_id.id)

    # шукаємо таск по x_odoo1_task_id
    existing_ids = Task2.search([("x_odoo1_task_id", "=", task_id_in_1)], limit=1)

    # мапимо stage_id по імені
    stage_id_in_2 = None
    if task1.stage_id:
        stage_id_in_2 = _map_task_stage_by_name(task1.stage_id, env2)

    vals_2 = {
        "name": task1.name,
        "user_id": task1.user_id.id or False,
        "date_deadline": task1.date_deadline or False,
        "kanban_state": task1.kanban_state or "normal",
        "company_id": task1.company_id.id or False,
        # зв’язуємо з проєктом в Odoo 2
        "project_id": project_id_in_2 or False,
        # поле-зв’язка
        "x_odoo1_task_id": task_id_in_1,
    }
    if stage_id_in_2:
        vals_2["stage_id"] = stage_id_in_2

    if existing_ids:
        task_id_in_2 = existing_ids[0]
        task2 = Task2.browse(task_id_in_2)
        task2.write(vals_2)
    else:
        task_id_in_2 = Task2.create(vals_2)

    # опційно — зворотнє посилання в Odoo 1
    if hasattr(task1, "x_odoo2_task_id"):
        task1.write({"x_odoo2_task_id": task_id_in_2})

    return task_id_in_2


# ==========
# Синк змін таску 2 → 1
# ==========


def sync_task_from_2_to_1(task_id_in_2: int) -> int:
    """
    Коли таск змінюється в Odoo 2 — ми оновлюємо відповідний таск у Odoo 1.

    Беремо лише таски, які мають x_odoo1_task_id.
    """
    env1 = odoo1_client.env
    env2 = odoo2_client.env

    Task1 = env1["project.task"]
    Task2 = env2["project.task"]

    task2 = Task2.browse(task_id_in_2)
    if not task2.exists():
        raise HTTPException(status_code=404, detail="task not found in Odoo 2")

    origin_id = getattr(task2, "x_odoo1_task_id", False)
    if not origin_id:
        raise HTTPException(
            status_code=400,
            detail="task in Odoo 2 has no x_odoo1_task_id, cannot sync back",
        )

    task1 = Task1.browse(origin_id)
    if not task1.exists():
        raise HTTPException(
            status_code=404,
            detail="original task not found in Odoo 1",
        )

    # мапимо stage_id назад по імені
    stage_id_in_1 = None
    if task2.stage_id:
        stage_id_in_1 = _map_task_stage_by_name(task2.stage_id, env1)

    vals_1 = {
        "name": task2.name,
        "user_id": task2.user_id.id or False,
        "date_deadline": task2.date_deadline or False,
        "kanban_state": task2.kanban_state or "normal",
    }
    if stage_id_in_1:
        vals_1["stage_id"] = stage_id_in_1

    # **важливо**: description в project.task — HTML-поле з історією,
    # в 18-ці воно інколи лагає при масових оновленнях.
    # Якщо треба — додаси сюди description, але якщо вилізуть ValidationError
    # про "different history for field 'description'" — просто прибери його.
    # vals_1["description"] = task2.description

    task1.write(vals_1)
    return origin_id


# ==========
# FastAPI endpoints
# ==========


@router.post(
    "/sync-project-from-1-to-2",
    response_model=SyncProjectFrom1To2Response,
)
def api_sync_project_from_1_to_2(payload: SyncProjectFrom1To2Request):
    """
    Викликається з Odoo 1 (сервер-екшн / automation), коли створили/оновили проект.
    """
    project_id_in_2 = sync_project_from_1_to_2(payload.project_id_in_1)
    return SyncProjectFrom1To2Response(project_id_in_2=project_id_in_2)


@router.post(
    "/sync-task-from-1-to-2",
    response_model=SyncTaskFrom1To2Response,
)
def api_sync_task_from_1_to_2(payload: SyncTaskFrom1To2Request):
    """
    Викликається з Odoo 1, коли створили/оновили таск.
    """
    task_id_in_2 = sync_task_from_1_to_2(payload.task_id_in_1)
    return SyncTaskFrom1To2Response(task_id_in_2=task_id_in_2)


@router.post(
    "/task-changed-in-2",
    response_model=TaskChangedIn2Response,
)
def api_task_changed_in_2(payload: TaskChangedIn2Request):
    """
    Викликається з Odoo 2, коли там змінили таск.
    """
    task_id_in_1 = sync_task_from_2_to_1(payload.task_id_in_2)
    return TaskChangedIn2Response(task_id_in_1=task_id_in_1)
