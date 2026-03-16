from fastapi import APIRouter, HTTPException
from app.config.manager import config_manager
from app.config.models import ViolationRule
from typing import List

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=List[ViolationRule])
async def list_rules():
    return config_manager.get_config().violation_rules


@router.post("", response_model=ViolationRule)
async def create_rule(rule: ViolationRule):
    rules = config_manager.get_config().violation_rules
    rules.append(rule)
    config_manager.update_rules(rules)
    return rule


@router.put("/{rule_id}", response_model=ViolationRule)
async def update_rule(rule_id: str, rule: ViolationRule):
    rules = config_manager.get_config().violation_rules
    for i, r in enumerate(rules):
        if r.id == rule_id:
            rules[i] = rule
            config_manager.update_rules(rules)
            return rule
    raise HTTPException(status_code=404, detail="Rule not found")


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str):
    rules = config_manager.get_config().violation_rules
    rules = [r for r in rules if r.id != rule_id]
    config_manager.update_rules(rules)
    return {"message": "Rule deleted"}
