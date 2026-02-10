"""Mock responses for Microsoft Graph API calls."""

USER_PROFILE = {
    "id": "user-123",
    "displayName": "Kevin Loyola",
    "mail": "kevin@example.com",
}

TODO_LISTS = {
    "value": [
        {"id": "list-hoy", "displayName": "Hoy"},
        {"id": "list-semana", "displayName": "Esta semana"},
        {"id": "list-espera", "displayName": "En espera"},
        {"id": "list-other", "displayName": "Otra lista"},
    ]
}

TASKS_HOY = {
    "value": [
        {
            "id": "task-simple-1",
            "title": "Pagar luz",
            "status": "notStarted",
            "body": {"contentType": "text", "content": ""},
            "dueDateTime": None,
            "lastModifiedDateTime": "2025-01-15T10:00:00Z",
            "createdDateTime": "2025-01-15T09:00:00Z",
        },
        {
            "id": "task-complex-1",
            "title": "Investigar opciones de migración a nueva arquitectura de microservicios",
            "status": "notStarted",
            "body": {"contentType": "text", "content": "Revisar AWS vs Azure"},
            "dueDateTime": {"dateTime": "2025-01-20T00:00:00.0000000", "timeZone": "UTC"},
            "lastModifiedDateTime": "2025-01-15T10:00:00Z",
            "createdDateTime": "2025-01-15T09:00:00Z",
        },
        {
            "id": "task-force-onenote",
            "title": "#onenote Revisar notas del sprint",
            "status": "notStarted",
            "body": {"contentType": "text", "content": ""},
            "dueDateTime": None,
            "lastModifiedDateTime": "2025-01-15T10:00:00Z",
            "createdDateTime": "2025-01-15T09:00:00Z",
        },
    ]
}

TASKS_SEMANA = {
    "value": [
        {
            "id": "task-semana-1",
            "title": "Preparar presentación del proyecto Q2",
            "status": "notStarted",
            "body": {"contentType": "text", "content": ""},
            "dueDateTime": {"dateTime": "2025-01-22T00:00:00.0000000", "timeZone": "UTC"},
            "lastModifiedDateTime": "2025-01-16T08:00:00Z",
            "createdDateTime": "2025-01-16T08:00:00Z",
        },
    ]
}

TASKS_ESPERA = {"value": []}

NOTEBOOKS = {
    "value": [
        {"id": "nb-123", "displayName": "My Notebook"},
    ]
}

SECTIONS = {
    "value": [
        {"id": "sec-hoy", "displayName": "Hoy"},
        {"id": "sec-semana", "displayName": "Esta semana"},
    ]
}

CREATED_SECTION = {"id": "sec-espera-new", "displayName": "En espera"}

CREATED_PAGE = {
    "id": "page-123",
    "title": "Test Page",
    "links": {
        "oneNoteWebUrl": {
            "href": "https://onenote.com/page-123"
        }
    },
}

PAGE_WITH_LINK = {
    "id": "page-123",
    "links": {
        "oneNoteWebUrl": {
            "href": "https://onenote.com/page-123"
        }
    },
}

CREATED_EVENT = {
    "id": "event-123",
    "subject": "[To Do] Test Task",
}

WEEKLY_REVIEW_EVENT = {
    "id": "event-weekly-123",
    "subject": "Revisión Semanal - Tareas",
}
