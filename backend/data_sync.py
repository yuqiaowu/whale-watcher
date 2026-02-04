import os
import subprocess
import datetime

def run_git_command(args, cwd=None, sensitive=False):
    try:
        log_args = ["***" if sensitive and i > 1 else arg for i, arg in enumerate(args)]
        
        result = subprocess.run(
            args, 
            cwd=cwd, 
            text=True, 
            capture_output=True, 
            check=True
        )
        if not sensitive:
            print(f"✅ Git: {' '.join(log_args)} -> {result.stdout.strip()[:50]}...")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Git Error: {e.stderr}")
        return False

def sync_data_to_github():
    """
    Simulates a git push to a separate 'data-history' branch.
    This prevents Railway from re-deploying (infinite loop) since Railway only watches 'main'.
    """
    
    # 1. 检查环境变量 (仅在云端或配置了Token的环境运行)
    github_token = os.getenv("GITHUB_TOKEN")
    repo_url = os.getenv("REPO_URL", "github.com/yuqiaowu/whale-watcher.git")
    
    # 如果是在本地开发环境且没有强制开启，为了安全起见，可以选择跳过，或者需要用户手动配置
    if not github_token:
        print("⚠️ GITHUB_TOKEN not found. Skipping auto-sync to GitHub.")
        return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "frontend", "data")
    
    print("🔄 Starting Data Sync to 'data-history' branch...")

    # 2. 配置 Git (临时的，仅对当前 commits 有效)
    run_git_command(["git", "config", "user.name", "Dolores AI"], cwd=base_dir)
    run_git_command(["git", "config", "user.email", "ai@whale-watcher.com"], cwd=base_dir)

    # 3. 构建带 Token 的 Remote URL
    # 格式: https://oauth2:TOKEN@github.com/user/repo.git
    # 注意安全：不要打印这个 URL
    auth_repo_url = f"https://oauth2:{github_token}@{repo_url.replace('https://', '')}"
    
    # 4. 切换/创建孤儿分支 (Orphan Branch) 或者普通分支
    # 我们尝试切到 data-history，如果不存在就创建
    # 注意：在 Railway 容器里，可能是一个浅克隆 (shallow clone)，操作 git 可能有限制
    # 我们采用简化的逻辑：直接 fetch 远程的 data-history (如果存在)，并在此基础上提交
    
    try:
        # Fetch relay to ensure we know about remote branches
        run_git_command(["git", "fetch", "origin"], cwd=base_dir)
        
        # 尝试切换到 data-history
        if not run_git_command(["git", "checkout", "data-history"], cwd=base_dir):
            #如果不成功，说明本地没有，尝试创建并追踪远程
            print("Creating new branch 'data-history'...")
            run_git_command(["git", "checkout", "-b", "data-history"], cwd=base_dir)
        else:
            # 如果成功切换，拉取最新
            run_git_command(["git", "pull", "origin", "data-history"], cwd=base_dir)

        # 5. 添加数据文件
        # 我们只同步 JSON 文件
        run_git_command(["git", "add", "frontend/data/whale_analysis.json"], cwd=base_dir)
        run_git_command(["git", "add", "frontend/data/market_data.json"], cwd=base_dir) # If exists
        
        # 6. Commit
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        if run_git_command(["git", "commit", "-m", f"Data Update: {timestamp} [skip ci]"], cwd=base_dir):
            # 7. Push
            # 这里的 [skip ci] 是双重保险，告诉 CI 工具不要构建
            print("🚀 Pushing to origin/data-history...")
            
            # 使用带 Token 的 URL 推送
            # subprocess 此时不会泄露 Token 到日志，因为我们在 run_git_command 里虽然打印了 args，
            # 但 auth_repo_url 是作为一个整体参数。为了即使在 args 打印时也不泄露，
            # 我们应该避免直接打印 args 如果它包含敏感信息。
            # 这里为了演示简单，我在 run_git_command 里打印了。
            # **生产环境应该修改 run_git_command 不打印含 Token 的 URL**
            
            # 临时修改 remote 防止打印
            run_git_command(["git", "remote", "set-url", "origin", auth_repo_url], cwd=base_dir, sensitive=True)
            run_git_command(["git", "push", "origin", "data-history"], cwd=base_dir)
            print("✅ Data Sync Completed Successfully!")
            
    except Exception as e:
        print(f"❌ Data Sync Failed: {e}")
    finally:
        # 切回 main (虽然容器可能马上就销毁了，但是个好习惯)
        run_git_command(["git", "checkout", "main"], cwd=base_dir)

if __name__ == "__main__":
    sync_data_to_github()
