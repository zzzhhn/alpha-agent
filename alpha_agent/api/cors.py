from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def install_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=[
            "*", "Authorization", "X-LLM-Provider", "X-LLM-API-Key",
            "X-LLM-Base-URL", "X-LLM-Model",
        ],
    )
