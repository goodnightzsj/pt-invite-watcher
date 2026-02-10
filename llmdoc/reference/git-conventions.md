# Git Conventions Reference

## Overview

本项目的 Git 工作流和提交规范。

## Commit Message Format

使用 Conventional Commits 规范：

```
<type>: <description>
```

### Types

| Type | Description | Example |
|------|-------------|---------|
| `feat` | 新功能 | `feat: add telegram notification` |
| `fix` | Bug 修复 | `fix: close response on all paths` |
| `refactor` | 代码重构 | `refactor: avoid holding httpx.Response` |
| `docs` | 文档变更 | `docs: update API reference` |
| `test` | 测试相关 | `test: add scanner unit tests` |
| `chore` | 构建/工具 | `chore: update dependencies` |
| `perf` | 性能优化 | `perf: cache site list` |

### Examples (from project history)

```
fix: init ws broadcaster queue in running loop
fix: make ws broadcaster queue ops best-effort on loop close
fix: use create_task_logged for cookiecloud finalize task
fix: close coroutine when create_task_logged called without running loop
feat: add --all-classes method audit to refactor gate
refactor: avoid holding httpx.Response for last_http errors
```

### Description Guidelines

- 使用英文
- 首字母小写
- 不使用句号结尾
- 使用祈使语气 (add, fix, update)
- 简洁描述变更内容

## Branch Strategy

### Main Branch

- `main`: 主分支，保持稳定

### Feature Branches (if used)

```
feature/add-wecom-notification
fix/scanner-timeout-issue
refactor/storage-layer
```

## Workflow

### 日常开发

```bash
# 1. 确保在最新代码上
git pull origin main

# 2. 进行修改
# ... edit files ...

# 3. 检查变更
git status
git diff

# 4. 暂存和提交
git add <specific-files>
git commit -m "fix: description of the fix"

# 5. 推送
git push origin main
```

### 资源泄漏修复示例

项目历史中有大量修复 HTTP 响应未关闭的提交：

```
fix: close mteam response on all paths
fix: close telegram response
fix: close moviepilot 401 response before retry
fix: close nexusphp registration responses
fix: close nexusphp invite responses
fix: close wecom responses
```

这体现了：
- 每个修复单独提交
- 描述具体修复的位置
- 使用一致的描述格式

## Best Practices

### 提交粒度

| Do | Don't |
|----|-------|
| 每个逻辑变更一个提交 | 一个提交包含多个不相关变更 |
| 小而完整的变更 | 提交不完整的代码 |
| 编译通过再提交 | 提交破坏构建的代码 |

### 提交前检查

```bash
# 运行类型检查
mypy pt_invite_watcher/

# 运行格式化
black pt_invite_watcher/
isort pt_invite_watcher/

# 运行测试
pytest
```

### .gitignore

项目忽略以下内容：

```
__pycache__/
*.pyc
.env
*.db
*.db-wal
*.db-shm
node_modules/
dist/
.vscode/
.idea/
```

## Changelog

版本变更通过 Git 标签管理：

```bash
# 创建版本标签
git tag -a v1.0.0 -m "Release 1.0.0"
git push origin v1.0.0
```

## Code Review

### PR 描述模板

```markdown
## Summary
简述变更内容

## Changes
- 变更点 1
- 变更点 2

## Testing
测试方法/结果

## Related Issues
#123
```

## Rollback

### 回滚单个提交

```bash
git revert <commit-hash>
```

### 强制回滚（谨慎使用）

```bash
git reset --hard <commit-hash>
git push --force  # 仅限个人分支
```
