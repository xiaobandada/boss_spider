import asyncio
import csv
import json
import os
from playwright.async_api import async_playwright

# ================= 配置区域 =================
KEYWORD = "Java"        # 你想搜的词
CITY_CODE = "101020100" # 城市代码（上海）。全国: 100010000, 北京: 101010100, 深圳: 101280600
PAGES = 3               # 抓取页数
# ============================================

async def fetch_jobs(keyword, city_code, pages):
    os.makedirs("results", exist_ok=True)
    output_file = f"results/BOSS_{keyword}_{pages}页.csv"
    
    async with async_playwright() as p:
        print("正在启动 Edge 浏览器，首次使用请在弹出的窗口里扫码登录...")
        
        # 使用持久化上下文，复用登录状态
        context = await p.chromium.launch_persistent_context(
            user_data_dir="./boss_data",
            headless=False,  
            channel="msedge",  # 直接调用你电脑上的 Edge
            viewport={"width": 1280, "height": 800}
        )
        
        page = await context.new_page()
        
        # 1. 打开 BOSS 直聘
        await page.goto("https://www.zhipin.com/web/geek/job", wait_until="domcontentloaded")
        
        # 等待页面加载，判断是否需要登录
        await page.wait_for_timeout(3000)
        if "登录" in await page.title() or "login" in page.url:
            print("⚠️ 检测到未登录，请在弹出的 Edge 窗口中扫码或输入密码登录！")
            print("等待登录中...（登录成功后程序会自动继续，最多等待 60 秒）")
            try:
                await page.wait_for_selector(".user-nav", timeout=60000)
                print("✅ 登录成功！开始抓取...")
            except Exception:
                print("❌ 登录超时，程序退出。")
                await context.close()
                return
        else:
            print("✅ 读取到历史登录状态，直接开始抓取...")

        all_jobs = []
        
        # 2. 循环翻页抓取
        for page_num in range(1, pages + 1):
            print(f"\n正在抓取第 {page_num} 页...")
            
            js_code = f"""
            (async function() {{
                const params = new URLSearchParams({{
                    query: "{keyword}",
                    city: "{city_code}",
                    page: "{page_num}",
                    pageSize: "30"
                }});
                const r = await fetch('/wapi/zpgeek/search/joblist.json?' + params.toString());
                const d = await r.json();
                if (d.code !== 0 || !d.zpData) return JSON.stringify({{ error: d.message || '无数据' }});
                return JSON.stringify(d.zpData.jobList || []);
            }})()
            """
            
            try:
                raw_data = await page.evaluate(js_code)
                data = json.loads(raw_data)
                
                if isinstance(data, dict) and "error" in data:
                    print(f"❌ 抓取失败：{data['error']}")
                    break
                    
                if not data:
                    print("⚠️ 没有更多数据了。")
                    break
                    
                for job in data:
                    skills = job.get('skills', [])
                    skill_str = "、".join(skills) if skills else "无要求"
                    
                    all_jobs.append({
                        "工作名称": job.get("jobName", ""),
                        "薪资待遇": job.get("salaryDesc", ""),
                        "公司名称": job.get("brandName", ""),
                        "行业/规模": f"{job.get('brandIndustry', '')} / {job.get('brandScaleName', '')}",
                        "区域": f"{job.get('cityName', '')} {job.get('areaDistrict', '')} {job.get('businessDistrict', '')}",
                        "技能要求": skill_str,
                        "福利标签": "、".join(job.get("welfareList", [])) or "无",
                        "详情链接": "https://www.zhipin.com" + job.get("jobUrl", "")
                    })
                
                print(f"✅ 第 {page_num} 页抓取成功，获取 {len(data)} 条数据。")
                
                if page_num < pages:
                    wait_time = 3
                    print(f"等待 {wait_time} 秒防止触发风控...")
                    await page.wait_for_timeout(wait_time * 1000)
                    
            except Exception as e:
                print(f"❌ 提取第 {page_num} 页时出错: {e}")
                break

        await context.close()
        
        # 3. 写入 CSV 文件
        if all_jobs:
            with open(output_file, mode="w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=all_jobs[0].keys())
                writer.writeheader()
                writer.writerows(all_jobs)
            print(f"\n🎉 抓取完成！共抓取 {len(all_jobs)} 条真实岗位数据。")
            print(f"📁 文件已保存至: {os.path.abspath(