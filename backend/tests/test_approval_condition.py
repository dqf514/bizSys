"""E1 条件求值升级：条件组（and/or，可嵌套）/ 数值区间 between / 集合 in / 空值 empty·not_empty。

覆盖两处求值器：
- ``app.modules.approval.condition.eval_condition``（流程分支，变量口径）
- ``app.modules.oa.service.eval_condition``（OA 表单条件，表单数据口径）
"""

from app.modules.approval.condition import eval_condition
from app.modules.oa.schemas import ConditionGroup
from app.modules.oa.service import eval_condition as oa_eval_condition


def _oa(group: dict, data: dict) -> bool:
    return oa_eval_condition(ConditionGroup.model_validate(group), data)


class TestEngineCondition:
    def test_scalar_ops(self):
        v = {"amount": 100, "name": "张三", "dept": "财务部"}
        assert eval_condition({"field": "amount", "op": "gt", "value": 50}, v)
        assert not eval_condition({"field": "amount", "op": "gt", "value": 100}, v)
        assert eval_condition({"field": "amount", "op": "gte", "value": 100}, v)
        assert eval_condition({"field": "name", "op": "eq", "value": "张三"}, v)
        assert eval_condition({"field": "name", "op": "contains", "value": "三"}, v)

    def test_between(self):
        v = {"amount": 5000}
        assert eval_condition({"field": "amount", "op": "between", "value": [1000, 10000]}, v)
        assert eval_condition({"field": "amount", "op": "between", "value": [1000, 10000]}, v)
        assert not eval_condition({"field": "amount", "op": "between", "value": [1000, 4000]}, v)
        assert eval_condition({"field": "amount", "op": "between", "value": {"min": 1000}}, v)

    def test_in_and_empty(self):
        v = {"dept": "财务部", "remark": ""}
        assert eval_condition({"field": "dept", "op": "in", "value": ["财务部", "总经办"]}, v)
        assert not eval_condition({"field": "dept", "op": "in", "value": ["总经办"]}, v)
        assert eval_condition({"field": "remark", "op": "empty"}, v)
        assert not eval_condition({"field": "remark", "op": "not_empty"}, v)
        assert eval_condition({"field": "dept", "op": "not_empty"}, v)

    def test_condition_group_and(self):
        expr = {
            "logic": "and",
            "rules": [
                {"field": "amount", "op": "gte", "value": 100000},
                {"field": "dept", "op": "eq", "value": "财务部"},
            ],
        }
        assert eval_condition(expr, {"amount": 200000, "dept": "财务部"})
        assert not eval_condition(expr, {"amount": 200000, "dept": "工程部"})

    def test_condition_group_or(self):
        expr = {
            "logic": "or",
            "rules": [
                {"field": "amount", "op": "gte", "value": 1000000},
                {"field": "level", "op": "eq", "value": "重大"},
            ],
        }
        assert eval_condition(expr, {"amount": 1, "level": "重大"})
        assert not eval_condition(expr, {"amount": 1, "level": "一般"})

    def test_nested_group(self):
        expr = {
            "logic": "and",
            "rules": [
                {"field": "amount", "op": "between", "value": [1000, 10000]},
                {
                    "logic": "or",
                    "rules": [
                        {"field": "dept", "op": "eq", "value": "财务部"},
                        {"field": "dept", "op": "eq", "value": "总经办"},
                    ],
                },
            ],
        }
        assert eval_condition(expr, {"amount": 5000, "dept": "总经办"})
        assert not eval_condition(expr, {"amount": 5000, "dept": "工程部"})
        assert not eval_condition(expr, {"amount": 50000, "dept": "总经办"})

    def test_empty_group_is_true(self):
        assert eval_condition({"logic": "and", "rules": []}, {})
        assert eval_condition(None, {})
        assert eval_condition({"default": True}, {})

    def test_form_prefix(self):
        assert eval_condition({"field": "form.amount", "op": "gt", "value": 10}, {"form": {"amount": 20}})


class TestOaCondition:
    def test_scalar_and_between(self):
        g = {"logic": "and", "rules": [{"field": "amount", "op": "between", "value": [1000, 10000]}]}
        assert _oa(g, {"amount": 5000})
        assert not _oa(g, {"amount": 50000})

    def test_checkbox_contains_semantics(self):
        g = {"logic": "and", "rules": [{"field": "tags", "op": "eq", "value": "A"}]}
        assert _oa(g, {"tags": ["A", "B"]})
        g2 = {"logic": "and", "rules": [{"field": "tags", "op": "ne", "value": "A"}]}
        assert _oa(g2, {"tags": ["B"]})

    def test_in_operator(self):
        g = {"logic": "and", "rules": [{"field": "dept", "op": "in", "value": ["财务部", "总经办"]}]}
        assert _oa(g, {"dept": "财务部"})
        assert not _oa(g, {"dept": "工程部"})

    def test_empty_operator(self):
        g = {"logic": "and", "rules": [{"field": "remark", "op": "empty"}]}
        assert _oa(g, {"remark": ""})
        assert not _oa(g, {"remark": "x"})

    def test_nested_group(self):
        g = {
            "logic": "and",
            "rules": [
                {"field": "amount", "op": "gte", "value": 100},
                {
                    "logic": "or",
                    "rules": [
                        {"field": "dept", "op": "eq", "value": "财务部"},
                        {"field": "dept", "op": "eq", "value": "总经办"},
                    ],
                },
            ],
        }
        assert _oa(g, {"amount": 200, "dept": "总经办"})
        assert not _oa(g, {"amount": 200, "dept": "工程部"})

    def test_unconfigured_group_is_true(self):
        assert _oa({"logic": "and", "rules": []}, {})
