import requests

session = requests.Session()
session.headers.update(
    {"Authorization": "Bearer 9d9634db-ecec-47fb-9880-11c086d70769"}
)


def get_data():
    return session.get("https://api.weeek.net/public/v1/ws").json()


def get_boards(project_id=""):

    return session.get(
        f"https://api.weeek.net/public/v1/tm/boards/",
        params={"projectId": project_id},
    ).json()


def get_projects(project_id=""):
    return session.get(
        f"https://api.weeek.net/public/v1/tm/projects/{project_id}"
    ).json()


def get_tasks(
    boardId: int, projectId: int, perPage: int = None, offset: int = None
):
    params = {
        "boardId": boardId,
        "projectId": projectId,
    }
    if perPage is not None:
        params["perPage"] = perPage
    if offset is not None:
        params["offset"] = offset

    return session.get(
        "https://api.weeek.net/public/v1/tm/tasks/",
        params=params,
    ).json()


def get_task(taskId: int):
    return session.get(
        f"https://api.weeek.net/public/v1/tm/tasks/",
        params={"taskId": taskId},
    ).json()


def get_boardColumn_list(boardId: int):
    return session.get(
        f"https://api.weeek.net/public/v1/tm/board-columns/",
        params={"boardId": boardId},
    ).json()


def create_task(project_id, column_id, title, description=""):
    return session.post(
        "https://api.weeek.net/public/v1/tm/tasks/",
        json={
            "locations": [
                {"projectId": project_id, "boardColumnId": column_id}
            ],
            "title": title,
            "description": description,
            "type": "action",
            "priority": 0,
        },
        headers={"Content-Type": "application/json"},
    ).json()


def get_assignees(board_id):
    return session.get("https://api.weeek.net/public/v1/ws/members").json()
