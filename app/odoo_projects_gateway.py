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
# НАЛАШТУВАННЯ МАПІНГУ КОРИСТУВАЧІВ
# ==========

# ЯВНИЙ mapping ID -> ID (підставиш свої)
USER_MAP_1_TO_2: dict[int, int] = {
    # приклад:
    # 2: 5,   # користувач з id=2 в Odoo1 відповідає id=5 в Odoo2
}

USER_MAP_2_TO_1: dict[int, int] = {
    # приклад:
    # 5: 2,
}

# Fallback-користувачі (якщо ні в мапі, ні по email/login не знайшли)
# Якщо не хочеш fallback'а — лиши None
USER_FALLBACK_1_TO_2: Optional[int] = None  # id користувача в Odoo2
USER_FALLBACK_2_TO_1: Optional[int] = None  # id користувача в Odoo1


def _map_user_1_to_2(user_1, env2) -> bool | int:
    """
    user_1 - browse record res.users з Odoo1
    Повертає:
      - int (user_id в Odoo2),
      - або False (нічого не ставимо).
    """
    if not user_1:
        return False

    # 1) явний mapping по ID
    if user_1.id in USER_MAP_1_TO_2:
        return USER_MAP_1_TO_2[user_1.id]

    Users2 = env2["res.users"]

    # 2) пробуємо знайти по login
    if getattr(user_1, "login", None):
        ids = Users2.search([("login", "=", user_1.login)], limit=1)
        if ids:
            return ids[0]

    # 3) пробуємо знайти по email
    if getattr(user_1, "email", None):
        ids = Users2.search([("email", "=", user_1.email)], limit=1)
        if ids:
            return ids[0]

    # 4) fallback
    if USER_FALLBACK_1_TO_2 is not None:
        return USER_FALLBACK_1_TO_2

    # 5) взагалі нікого не ставимо
    return False


def _map_user_2_to_1(user_2, env1) -> bool | int:
    """
    user_2 - browse record res.users з Odoo2.
    Аналогічно _map_user_1_to_2, але в зворотній бік.
    """
    if not user_2:
        return False

    if user_2.id in USER_MAP_2_TO_1:
        return USER_MAP_2_TO_1[user_2.id]

    Users1 = env1["res.users"]

    if getattr(user_2, "login", None):
        ids = Users1.search([("login", "=", user_2.login)], limit=1)
        if ids:
            return ids[0]

    if getattr(user_2, "email", None):
        ids = Users1.search([("email", "=", user_2.email)], limit=1)
        if ids:
            return ids[0]

    if USER_FALLBACK_2_TO_1 is not None:
        return USER_FALLBACK_2_TO_1

    return False


# ==========
# Інші допоміжні функції
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

    Зв’язки:
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

    # мапимо user_id
    user_id_in_2 = _map_user_1_to_2(proj1.user_id, env2)

    vals_2 = {
        "name": proj1.name,
        "partner_id": proj1.partner_id.id or False,
        "user_id": user_id_in_2,
        "company_id": proj1.company_id.id or False,
        "x_odoo1_project_id": project_id_in_1,
    }

    if existing_ids:
        project_id_in_2 = existing_ids[0]
        proj2 = Project2.browse(project_id_in_2)
        proj2.write(vals_2)
    else:
        project_id_in_2 = Project2.create(vals_2)

    # зворотній ID в Odoo1, якщо поле існує
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
    """
    env1 = odoo1_client.env
    env2 = odoo2_client.env

    Task1 = env1["project.task"]
    Task2 = env2["project.task"]

    task1 = Task1.browse(task_id_in_1)
    if not task1.exists():
        raise HTTPException(status_code=404, detail="task not found in Odoo 1")

    # проєкт теж синкаємо
    project_id_in_2 = None
    if task1.project_id:
        project_id_in_2 = sync_project_from_1_to_2(task1.project_id.id)

    existing_ids = Task2.search([("x_odoo1_task_id", "=", task_id_in_1)], limit=1)

    stage_id_in_2 = None
    if task1.stage_id:
        stage_id_in_2 = _map_task_stage_by_name(task1.stage_id, env2)

    # мап юзера
    user_id_in_2 = _map_user_1_to_2(task1.user_id, env2)

    vals_2 = {
        "name": task1.name,
        "user_id": user_id_in_2,
        "date_deadline": task1.date_deadline or False,
        "kanban_state": task1.kanban_state or "normal",
        "company_id": task1.company_id.id or False,
        "project_id": project_id_in_2 or False,
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

    if hasattr(task1, "x_odoo2_task_id"):
        task1.write({"x_odoo2_task_id": task_id_in_2})

    return task_id_in_2


# ==========
# Синк змін таску 2 → 1
# ==========


def sync_task_from_2_to_1(task_id_in_2: int) -> int:
    """
    Коли таск змінюється в Odoo 2 — оновлюємо відповідний таск у Odoo 1.
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

    stage_id_in_1 = None
    if task2.stage_id:
        stage_id_in_1 = _map_task_stage_by_name(task2.stage_id, env1)

    # мап юзера назад
    user_id_in_1 = _map_user_2_to_1(task2.user_id, env1)

    vals_1 = {
        "name": task2.name,
        "user_id": user_id_in_1,
        "date_deadline": task2.date_deadline or False,
        "kanban_state": task2.kanban_state or "normal",
    }
    if stage_id_in_1:
        vals_1["stage_id"] = stage_id_in_1

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
    project_id_in_2 = sync_project_from_1_to_2(payload.project_id_in_1)
    return SyncProjectFrom1To2Response(project_id_in_2=project_id_in_2)


@router.post(
    "/sync-task-from-1-to-2",
    response_model=SyncTaskFrom1To2Response,
)
def api_sync_task_from_1_to_2(payload: SyncTaskFrom1To2Request):
    task_id_in_2 = sync_task_from_1_to_2(payload.task_id_in_1)
    return SyncTaskFrom1To2Response(task_id_in_2=task_id_in_2)


@router.post(
    "/task-changed-in-2",
    response_model=TaskChangedIn2Response,
)
def api_task_changed_in_2(payload: TaskChangedIn2Request):
    task_id_in_1 = sync_task_from_2_to_1(payload.task_id_in_2)
    return TaskChangedIn2Response(task_id_in_1=task_id_in_1)
