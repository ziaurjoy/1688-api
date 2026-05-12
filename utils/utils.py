from fastapi import Request

def get_project_url(request: Request):
    return str(request.base_url)