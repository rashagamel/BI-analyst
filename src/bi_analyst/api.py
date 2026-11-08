from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .runner import BIAnalyst


class AskRequest(BaseModel):
    question: str


def create_app(analyst: BIAnalyst | None = None) -> FastAPI:
    app = FastAPI(title="Multi-Agent BI Analyst")
    holder: dict[str, BIAnalyst] = {}

    def get() -> BIAnalyst:
        if analyst is not None:
            return analyst
        if "a" not in holder:
            holder["a"] = BIAnalyst()
        return holder["a"]

    @app.post("/ask")
    def ask(req: AskRequest) -> dict:
        return get().ask(req.question)

    @app.get("/schema")
    def schema() -> dict:
        return {"schema": get().schema.render()}

    return app


app = create_app()  # uvicorn bi_analyst.api:app
