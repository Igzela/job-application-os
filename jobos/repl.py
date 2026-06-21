"""Interactive REPL for Job Application OS — Hermes-style.

Rich rendering + prompt_toolkit + box-drawing characters.
Usage: job tui
"""

import json
import os
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .workspace import (
    APPLICATIONS_DIR,
    JOBS_DIR,
    PREDICTIONS_DIR,
    RETROS_DIR,
    jobs_normalized_dir,
    jobs_raw_dir,
    load_state,
    save_state,
    state_path as workspace_state_path,
)

console = Console()


def _banner():
    console.print(Panel(
        Text("求职操作系统  v0.1", style="bold cyan"),
        subtitle="[dim]输入 /help 查看命令[/dim]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 2),
    ))
    console.print()


class CmdCompleter(Completer):
    COMMANDS = [
        "/help", "/jobs", "/job", "/start", "/chat", "/import", "/boss",
        "/profile", "/config", "/settings", "/status", "/quit",
    ]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        for cmd in self.COMMANDS:
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text))


def run_repl(state_dir: str):
    root = Path(state_dir)
    history = FileHistory(str(root / ".repl_history"))
    session = PromptSession(history=history, completer=CmdCompleter())

    _banner()

    while True:
        try:
            line = session.prompt("job> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见！[/dim]")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        dispatch = {
            "/help": lambda: _cmd_help(),
            "/jobs": lambda: _cmd_jobs(root),
            "/job": lambda: _cmd_job(root, args),
            "/start": lambda: _cmd_start(root, args),
            "/chat": lambda: _cmd_chat(root, args),
            "/import": lambda: _cmd_import(root, args),
            "/boss": lambda: _cmd_boss(root, args),
            "/profile": lambda: _cmd_profile(root, args),
            "/config": lambda: _cmd_config(root, args),
            "/settings": lambda: _cmd_settings(root),
            "/status": lambda: _cmd_status(root),
            "/quit": lambda: None,
        }

        if cmd == "/quit":
            console.print("[dim]再见！[/dim]")
            break

        handler = dispatch.get(cmd)
        if handler:
            handler()
        else:
            console.print(f"[red]未知命令:[/red] {cmd}  输入 /help 查看可用命令")


# ═══════════════════════════════════════════════════════════════
#  Commands
# ═══════════════════════════════════════════════════════════════

def _cmd_help():
    console.print()
    console.print(Panel(
        Text("使用指南", style="bold"),
        border_style="cyan",
        box=box.ROUNDED,
    ))

    sections = [
        ("配置系统", [
            ("/config", "查看当前所有配置"),
            ("/config wizard", "运行配置向导（推荐首次使用）"),
            ("/config set <key> <值>", "修改配置项"),
            ("/config get <key>", "查看某个配置项"),
        ], "可配置: llm.provider, llm.model, llm.base_url, browser.cdp_url, submit.min_delay 等"),

        ("配置档案", [
            ("/profile", "查看档案文件列表"),
            ("/profile 1", "查看 base.yaml（姓名、学历、城市）"),
            ("/profile edit 1", "编辑 base.yaml"),
            ("/profile 2", "查看 skills.yaml（技能）"),
            ("/profile edit 2", "编辑 skills.yaml"),
        ], "你的个人信息，系统据此匹配职位"),

        ("导入职位", [
            ("/boss <关键词>", "从BOSS直聘搜索并导入"),
            ("/import <文件>", "从本地JD文件导入"),
            ("/jobs", "查看所有已导入的职位"),
            ("/job <id>", "查看某个职位的详情"),
        ], "搜索 → 分析 → 生成简历 → 自动投递"),

        ("全流程", [
            ("/start <关键词>", "一键：搜索→分析→生成招呼语→投递"),
            ("/start --dry-run", "只分析不投递"),
            ("/start --max 5", "最多投递5个"),
        ], "连接Chrome，自动完成整个求职流程"),

        ("AI助手", [
            ("/chat", "和AI聊天（问职位、优化简历、反诈分析）"),
            ("/chat 然后 /exit", "退出对话"),
        ], "AI可以帮你分析职位、优化档案、生成简历"),

        ("系统", [
            ("/settings", "健康检查：Chrome、档案完整性"),
            ("/status", "职位统计"),
            ("/quit", "退出"),
        ], None),
    ]

    for title, cmds, note in sections:
        t = Table(box=box.SIMPLE_HEAVY, show_header=False, padding=(0, 1))
        t.add_column("命令", style="bold yellow", min_width=25)
        t.add_column("说明")
        for cmd, desc in cmds:
            t.add_row(cmd, desc)
        console.print(Panel(t, title=f"[bold]{title}[/bold]", border_style="dim"))
        if note:
            console.print(f"  [dim]{note}[/dim]")
        console.print()

    console.print(Panel(
        Text("快速开始", style="bold green"),
        border_style="green",
        box=box.ROUNDED,
    ))
    steps = [
        "1. /config wizard        — 配置AI模型和API Key",
        "2. /profile edit 1       — 填写你的基本信息",
        "3. /profile edit 2       — 填写你的技能",
        "4. /boss Python开发      — 搜索职位",
        "5. /jobs                 — 查看结果",
        "6. /start Python开发     — 一键投递",
    ]
    for s in steps:
        console.print(f"  {s}")
    console.print()


def _cmd_jobs(root: Path):
    f = workspace_state_path(root)
    if not f.exists():
        console.print("[dim]暂无职位。用 /boss 或 /import 导入。[/dim]")
        return
    state = load_state(root)
    jobs = state.get("jobs", {})
    if not jobs:
        console.print("[dim]暂无职位。[/dim]")
        return

    t = Table(box=box.ROUNDED, border_style="cyan")
    t.add_column("ID", style="dim", max_width=14)
    t.add_column("职位", style="bold")
    t.add_column("公司")
    t.add_column("状态")
    t.add_column("分数", justify="right")

    status_colors = {
        "imported": "yellow", "scored": "blue", "predicted": "cyan",
        "packed": "green", "submitted": "bold green",
    }

    for jid, j in jobs.items():
        scores = j.get("scores", {})
        score = scores.get("final_score", "-")
        if isinstance(score, float):
            score = f"{score:.1f}"
        status = j.get("status", "?")
        color = status_colors.get(status, "white")
        t.add_row(
            jid[:13],
            j.get("title", "?")[:30],
            j.get("company", "?")[:18],
            f"[{color}]{status}[/{color}]",
            str(score),
        )

    console.print(t)
    console.print(f"\n[dim]共 {len(jobs)} 个职位[/dim]\n")


def _cmd_job(root: Path, args):
    if not args:
        console.print("[yellow]用法:[/yellow] /job <job_id>")
        return
    jid = args[0]
    f = workspace_state_path(root)
    if not f.exists():
        console.print("[dim]无状态文件。[/dim]")
        return
    state = load_state(root)
    j = state.get("jobs", {}).get(jid)
    if not j:
        console.print(f"[red]未找到:[/red] {jid}")
        return

    info = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    info.add_column("字段", style="bold cyan", min_width=8)
    info.add_column("值")
    info.add_row("职位", j.get("title", "?"))
    info.add_row("公司", j.get("company", "?"))
    info.add_row("地点", j.get("location", "?"))
    info.add_row("状态", j.get("status", "?"))
    info.add_row("来源", j.get("source", "?"))
    if j.get("link"):
        info.add_row("链接", j["link"])
    console.print(info)

    scores = j.get("scores", {})
    if scores:
        console.print()
        st = Table(box=box.SIMPLE_HEAVY, title="[bold]评分[/bold]")
        st.add_column("维度", style="bold")
        st.add_column("分数", justify="right")
        st.add_column("条形图")
        for dim in ["fit", "evidence", "opportunity", "strategic", "friction", "risk"]:
            val = scores.get(dim)
            if val is not None:
                bar = "█" * int(val) + "░" * (10 - int(val))
                st.add_row(dim, f"{val:.1f}", bar)
        if "final_score" in scores:
            st.add_row("[bold]总分[/bold]", f"[bold]{scores['final_score']:.2f}[/bold]", "")
        console.print(st)
    console.print()


def _cmd_start(root: Path, args):
    keyword = ""
    max_jobs = 10
    dry_run = False

    i = 0
    while i < len(args):
        if args[i] == "--keyword" and i + 1 < len(args):
            keyword = args[i + 1]; i += 2
        elif args[i] == "--max" and i + 1 < len(args):
            max_jobs = int(args[i + 1]); i += 2
        elif args[i] == "--dry-run":
            dry_run = True; i += 1
        else:
            keyword = args[i]; i += 1

    if not keyword:
        keyword = console.input("[bold cyan]搜索关键词:[/bold cyan] ").strip()
        if not keyword:
            return

    mode = "模拟" if dry_run else "真实"
    console.print(Panel(
        f"关键词: [bold]{keyword}[/bold]  最大: {max_jobs}  模式: [yellow]{mode}[/yellow]",
        title="[bold]🚀 启动全流程[/bold]",
        border_style="green",
    ))

    from jobos.orchestrator import run_full_pipeline
    result = run_full_pipeline(str(root), cdp_port=9222, max_jobs=max_jobs,
                               dry_run=dry_run, search_keyword=keyword)

    console.print()
    t = Table(box=box.ROUNDED, border_style="green", title="[bold]📊 结果[/bold]")
    t.add_column("职位", style="bold")
    t.add_column("结果")
    for r in result.get("results", []):
        j = r.get("job", {})
        status = r.get("status", "?")
        color = "green" if status in ("submitted", "dry_run") else "red" if "error" in status else "yellow"
        t.add_row(j.get("title", "?")[:30], f"[{color}]{status}[/{color}]")
    console.print(t)
    console.print(f"\n找到: {result.get('total_found', 0)}  投递: {result.get('submitted', 0)}\n")


def _cmd_chat(root: Path, args):
    from jobos.llm.provider import get_llm_adapter
    from jobos.llm.conversation import Conversation
    from jobos.llm.prompts import INTRO_SYSTEM

    llm = get_llm_adapter()
    hpath = root / "profile" / "chat_history.json"
    conv = Conversation(llm, hpath)

    console.print(Panel("[bold]AI对话模式[/bold]  输入 /exit 退出", border_style="cyan"))
    console.print()

    while True:
        try:
            text = console.input("[bold cyan]你>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text in ("/exit", "/quit", ""):
            break
        try:
            reply = conv.chat(text, system=INTRO_SYSTEM)
            console.print(f"[bold green]AI:[/bold green] {reply}\n")
        except Exception as e:
            console.print(f"[red]错误:[/red] {e}\n")


def _cmd_import(root: Path, args):
    if not args:
        path = console.input("[bold cyan]文件路径:[/bold cyan] ").strip()
    else:
        path = args[0]
    if not path:
        return

    from jobos.importer import import_job
    try:
        data = import_job(path, str(jobs_normalized_dir(root)))
        state = load_state(root)
        state["jobs"][data["job_id"]] = {"title": data["title"], "company": data["company"],
                                           "status": "imported", "location": data.get("location", "")}
        save_state(root, state)
        console.print(f"[green]✅[/green] {data['title']} @ {data['company']}")
    except Exception as e:
        console.print(f"[red]❌ {e}[/red]")


def _cmd_boss(root: Path, args):
    kw = " ".join(args) if args else console.input("[bold cyan]关键词:[/bold cyan] ").strip()
    if not kw:
        return

    from jobos.boss_import import import_from_boss
    import re
    from datetime import datetime, timezone

    console.print(f"[cyan]🔍 搜索 '{kw}'...[/cyan]")
    try:
        jobs = import_from_boss(kw, "100010000", 9222)
        if not jobs:
            console.print("[dim]未找到职位。[/dim]")
            return

        raw_dir = jobs_raw_dir(root)
        raw_dir.mkdir(parents=True, exist_ok=True)
        state = load_state(root)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        for i, job in enumerate(jobs):
            slug = re.sub(r"[^a-z0-9]+", "-", job["title"].lower()).strip("-")[:40]
            jid = f"{ts}-boss-{i:03d}-{slug}"
            (raw_dir / f"{jid}.json").write_text(json.dumps(job, indent=2, ensure_ascii=False))
            state["jobs"][jid] = {"title": job["title"], "company": job["company"],
                                   "status": "imported", "source": "boss_zhipin", "link": job.get("link", "")}

        save_state(root, state)

        t = Table(box=box.ROUNDED, border_style="green", title=f"[bold]✅ 导入 {len(jobs)} 个职位[/bold]")
        t.add_column("职位", style="bold")
        t.add_column("公司")
        t.add_column("薪资")
        for job in jobs:
            t.add_row(job["title"][:30], job["company"][:18], job.get("salary", ""))
        console.print(t)
    except Exception as e:
        console.print(f"[red]❌ {e}[/red]")


def _cmd_profile(root: Path, args):
    profile_dir = root / "profile"
    files = ["base.yaml", "skills.yaml", "availability.yaml", "evidence_bank.md"]
    labels = ["基本信息", "技能", "时间/薪资", "经历库"]

    if not args:
        t = Table(box=box.ROUNDED, border_style="cyan", title="[bold]👤 档案文件[/bold]")
        t.add_column("#", style="bold yellow", width=3)
        t.add_column("文件")
        t.add_column("说明")
        t.add_column("状态")
        for i, (f, label) in enumerate(zip(files, labels)):
            path = profile_dir / f
            status = "[green]✅ 已填写[/green]" if path.exists() else "[red]❌ 未创建[/red]"
            t.add_row(str(i + 1), f, label, status)
        console.print(t)
        console.print("\n[dim]/profile <编号> 查看  |  /profile edit <编号> 编辑[/dim]\n")
        return

    if args[0] == "edit" and len(args) > 1:
        idx = int(args[1]) - 1
        if 0 <= idx < len(files):
            path = profile_dir / files[idx]
            console.print(f"[bold]编辑 {files[idx]}[/bold] (输入内容，空行结束):")
            lines = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line == "":
                    break
                lines.append(line)
            if lines:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(lines) + "\n")
                console.print(f"[green]✅ 已保存 {files[idx]}[/green]")
        return

    try:
        idx = int(args[0]) - 1
        if 0 <= idx < len(files):
            path = profile_dir / files[idx]
            if path.exists():
                console.print(Panel(path.read_text(), title=f"[bold]{files[idx]}[/bold]", border_style="cyan"))
            else:
                console.print(f"[dim]{files[idx]} 不存在[/dim]")
    except (ValueError, IndexError):
        console.print("[yellow]用法:[/yellow] /profile [1-4] 或 /profile edit [1-4]")


def _cmd_config(root: Path, args):
    from jobos.config import print_config, set_config_value, get_config_value, config_wizard, CONFIG_FILE, ENV_FILE

    if not args:
        console.print(Panel("[bold]/config — 系统配置[/bold]", border_style="cyan"))
        console.print()
        t = Table(box=box.SIMPLE_HEAVY, show_header=False, padding=(0, 1))
        t.add_column("命令", style="bold yellow", min_width=28)
        t.add_column("说明")
        t.add_row("/config", "查看当前所有配置")
        t.add_row("/config wizard", "运行配置向导（推荐首次使用）")
        t.add_row("/config set <key> <值>", "修改配置项")
        t.add_row("/config get <key>", "查看某个配置项")
        t.add_row("/config path", "查看配置文件路径")
        console.print(t)
        console.print()

        ct = Table(box=box.ROUNDED, title="[bold]可配置项[/bold]", border_style="dim")
        ct.add_column("配置项", style="bold yellow")
        ct.add_column("说明")
        ct.add_column("默认值", style="dim")
        ct.add_row("llm.provider", "AI提供商", "anthropic")
        ct.add_row("llm.model", "模型名称", "mimo-v2.5")
        ct.add_row("llm.base_url", "API地址", "(自动读取)")
        ct.add_row("llm.temperature", "创造性 0-1", "0.7")
        ct.add_row("browser.cdp_url", "Chrome调试端口", "localhost:9222")
        ct.add_row("browser.headless", "无头模式", "false")
        ct.add_row("submit.min_delay", "投递间隔最小秒", "30")
        ct.add_row("submit.max_delay", "投递间隔最大秒", "120")
        ct.add_row("search.default_city", "默认城市", "全国")
        ct.add_row("scoring.min_score_to_apply", "最低投递分数", "60")
        console.print(ct)
        console.print()
        console.print(f"[dim]配置文件: {CONFIG_FILE}  |  密钥文件: {ENV_FILE}[/dim]\n")
        return

    if args[0] == "wizard":
        config_wizard()
    elif args[0] == "set" and len(args) >= 3:
        key = args[1]
        value = " ".join(args[2:])
        set_config_value(key, value)
        console.print(f"[green]✅[/green] {key} = {value}")
    elif args[0] == "get" and len(args) >= 2:
        val = get_config_value(args[1])
        console.print(f"{args[1]} = [bold]{val}[/bold]")
    elif args[0] in ("show", "list"):
        if not CONFIG_FILE.exists():
            console.print(f"[dim]配置文件不存在: {CONFIG_FILE}[/dim]")
            console.print("[dim]运行 /config wizard 进行初始配置。[/dim]")
            return
        print_config()
    elif args[0] == "path":
        console.print(f"配置文件: [bold]{CONFIG_FILE}[/bold]")
        console.print(f"密钥文件: [bold]{ENV_FILE}[/bold]")
    else:
        console.print("[yellow]用法:[/yellow] /config [show|set|get|wizard|path]")


def _cmd_settings(root: Path):
    t = Table(box=box.ROUNDED, border_style="cyan", title="[bold]🏥 健康检查[/bold]")
    t.add_column("项目")
    t.add_column("状态")

    for d in ["profile", JOBS_DIR, PREDICTIONS_DIR, APPLICATIONS_DIR, RETROS_DIR, "rubrics"]:
        ok = (root / d).is_dir()
        t.add_row(f"{d}/", "[green]✅[/green]" if ok else "[red]❌[/red]")

    for f in ["base.yaml", "skills.yaml"]:
        ok = (root / "profile" / f).exists()
        t.add_row(f"profile/{f}", "[green]✅[/green]" if ok else "[red]❌[/red]")

    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:9222/json/version", timeout=2)
        t.add_row("Chrome CDP", "[green]✅ 可用[/green]")
    except Exception:
        t.add_row("Chrome CDP", "[red]❌ 不可用[/red]")

    console.print(t)
    console.print()


def _cmd_status(root: Path):
    f = workspace_state_path(root)
    if not f.exists():
        console.print("[dim]无状态数据。[/dim]")
        return
    state = load_state(root)
    jobs = state.get("jobs", {})
    counts = {}
    for j in jobs.values():
        s = j.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1

    t = Table(box=box.ROUNDED, border_style="cyan", title="[bold]📊 系统状态[/bold]")
    t.add_column("指标", style="bold")
    t.add_column("值", justify="right")
    t.add_row("职位总数", str(len(jobs)))
    for status, count in sorted(counts.items()):
        t.add_row(f"  {status}", str(count))
    t.add_row("活跃Rubric", state.get("active_rubric", "?"))
    t.add_row("机会数", str(len(state.get("opportunities", []))))
    console.print(t)
    console.print()
