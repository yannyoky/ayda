from ayda.main import API_PREFIX, create_app
from tests.contract import HTTP_METHODS, operations


def test_every_route_is_in_the_contract() -> None:
    contract_ops = {(m, p): op_id for op_id, (m, p, _) in operations().items()}
    schema = create_app().openapi()

    for path, item in schema["paths"].items():
        assert path.startswith(API_PREFIX), path
        for method in HTTP_METHODS:
            if method not in item:
                continue
            key = (method, path.removeprefix(API_PREFIX))
            assert key in contract_ops, f"{key} is not in contracts/openapi.yaml"
            assert item[method]["operationId"] == contract_ops[key], key
