#!/usr/bin/env python3
"""A stand-in for an internal HR/finance system, exposed over MCP (stdio).

Two tools, deterministic data, no network. The point of the demo is that the
agent decides which tool to call and passes the arguments itself -- not that
the data behind the tool is real.
"""
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

EMPLOYEES = {
    "E-1042": {"name": "Kim Min-jun", "department": "Engineering", "entitlement": 18, "taken": 11.5, "carried_over": 3},
    "E-2087": {"name": "Park Ji-woo", "department": "Finance", "entitlement": 15, "taken": 4, "carried_over": 0},
    "E-3311": {"name": "Lee Seo-yeon", "department": "Engineering", "entitlement": 21, "taken": 20, "carried_over": 5},
}

BUDGETS = {
    ("Engineering", 2026): {"allocated": 480_000_000, "committed": 431_500_000},
    ("Finance", 2026): {"allocated": 120_000_000, "committed": 62_000_000},
    ("Engineering", 2025): {"allocated": 410_000_000, "committed": 408_900_000},
}

app = Server("internal-systems")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_leave_balance",
            description=(
                "Look up an employee's remaining annual leave. "
                "Returns entitlement, days already taken, days carried over and the balance."
            ),
            inputSchema={
                "type": "object",
                "properties": {"employee_id": {"type": "string", "description": "Employee id, e.g. E-1042"}},
                "required": ["employee_id"],
            },
        ),
        Tool(
            name="get_department_budget",
            description=(
                "Look up a department's budget for a financial year. "
                "Returns the allocated amount, the amount already committed, and what remains, in KRW."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "Department name, e.g. Engineering"},
                    "year": {"type": "integer", "description": "Financial year, e.g. 2026"},
                },
                "required": ["department", "year"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_leave_balance":
        emp = EMPLOYEES.get(str(arguments.get("employee_id", "")).upper())
        if not emp:
            return [TextContent(type="text", text=f"No employee found with id {arguments.get('employee_id')!r}.")]
        balance = emp["entitlement"] + emp["carried_over"] - emp["taken"]
        return [TextContent(type="text", text=(
            f"{emp['name']} ({emp['department']}): entitlement {emp['entitlement']} days, "
            f"carried over {emp['carried_over']} days, taken {emp['taken']} days, "
            f"remaining balance {balance} days."
        ))]

    if name == "get_department_budget":
        dept = str(arguments.get("department", "")).title()
        year = int(arguments.get("year", 0))
        row = BUDGETS.get((dept, year))
        if not row:
            known = ", ".join(f"{d} {y}" for d, y in BUDGETS)
            return [TextContent(type="text", text=f"No budget on file for {dept} {year}. Available: {known}.")]
        remaining = row["allocated"] - row["committed"]
        return [TextContent(type="text", text=(
            f"{dept} {year}: allocated {row['allocated']:,} KRW, committed {row['committed']:,} KRW, "
            f"remaining {remaining:,} KRW."
        ))]

    return [TextContent(type="text", text=f"Unknown tool {name!r}.")]


async def main() -> None:
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
