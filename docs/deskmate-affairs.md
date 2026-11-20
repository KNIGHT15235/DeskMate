# DeskMate R4 个人资料整理

正常桌面入口接受一条任务中的公开网页 URL、选定工作区里的材料以及预期的 Markdown 路径。原 CLI/TUI 继续使用编程配置，`python -m likecc.desktop --demo` 继续运行原有离线演示和 DemoWait。

## 支持范围与权限

| 操作 | 约定 |
| --- | --- |
| 本地读取 | UTF-8 `.txt`、`.md`、`.markdown` 普通文件。使用解析后的工作区路径，排除应用配置和隐藏目录、网络路径及替代数据流。文件外链按解析后的目标检查。每文件最多 128 KiB，一次返回最多 6,500 正文字符，部分读取会标记截断 |
| 网页读取 | 每个任务最多接纳用户本条消息明确给出的 8 个 HTTP(S) URL，建议每行一个。支持静态 HTML、纯文本和 Markdown。HTML 提取正文和标题，跳过脚本、样式等内容，无动态渲染、搜索或登录态 |
| 网页资源限制 | 总时限 20 秒，HTTP I/O 8 秒、连接 5 秒，最多 3 跳重定向。检查响应类型和字节数，最多 512 KiB，拒绝压缩响应。正文输出最多 6,500 字符，未完成的读取以失败或中断记录 |
| Markdown 输出 | WriteFile 只写工作区内 Markdown，最大 128 KiB（含工具追加的来源）。写入默认询问，覆盖前必须实际读过目标，文件变化需要重读。ReadFile 回读本次输出时比较全文摘要 |
| 扩展 | Bash、EditFile、Glob 与 Grep 在资料配置下关闭。仍支持显式开启的 Skills、MCP、Hooks、memory、summaries。用户应把显式开启的外部扩展视作可信能力；本轮验收关闭这五项 |

网页默认按 URL 询问一次。`FetchWebPage(https://example.org/*)` 可作为规则模式，显式拒绝优先于放行，重定向目标也检查拒绝规则。批准起始 URL 允许剩余跳数内的公开重定向。工具拒绝用户密码、非 HTTP(S)、本机和非公网地址；解析结果包含非公网地址时不发请求。HTTP 连接使用已检查的数字 IP，保留原 Host、TLS SNI 和证书校验。每跳独立创建 HTTPX client，不继承代理环境、浏览器 Cookie、Provider 请求头或上次跳转的 Cookie。域名解析使用操作系统配置，固定 IP 约束本次实际连接；路由、恶意本机、站点内容和特殊网络环境仍有各自边界。

只使用公开 URL，查询字符串与地址可能出现在会话与成果记录中。资料中的指令由模型视为不可信文本，实际工具仍执行工作区、URL 与权限约束。工作区路径校验沿用解析后的路径检查；并发外部改动下没有 OS 级沙箱保证。开启外部扩展会引入其自身能力和信任边界。

## 怎么判断成果是否生成

来源 ID 如 `S1`、`S2` 来自本次实际 ReadFile / FetchWebPage 工具结果。会话中可查看 URL、最终地址、标题、时间和状态，本地来源使用相对路径。WriteFile 追加「来源（工具记录）」一节，拒绝把已知失败或未知 ID 写成 `[S编号]` 引用。正文与原资料是否相符仍需阅读核对。

成果面板按实际副作用显示「已写入，待回读」「已回读核对」或「回读未通过」。读取失败、拒绝写入或只输出聊天文本时可从工具历史看到原因。任务完成和成果回读分别显示。取消释放当前 HTTP 流与 client，随后可发新任务。历史恢复只读旧记录，不触发联网或写文件，来源摘要和授权范围随新任务重置。

## 离线验证与本机产物

在仓库根目录、现有 Conda 环境运行：

```bash
python -m examples.deskmate_materials
python -m examples.deskmate_materials --deny-write
```

也可给 `--work-dir` 一个已存在的空目录来保留产物。离线例使用确定性 fake client、注入 resolver 和 HTTP transport，以及真实权限事件、文件写入和回读。正常示例的实际产物为 `.r1-verification/r4-offline-Y0wZmt/outputs/study-plan.md`，回读状态 `verified`，三个来源均成功。拒绝示例目录 `.r1-verification/r4-denied-ySwMKO` 中没有成果文件。目录均在 Git 忽略范围内。

## 真实人工验收的起点

验收材料为 IANA 的 [Example Domains](https://www.iana.org/help/example-domains) 和 [IANA-managed Reserved Domains](https://www.iana.org/domains/reserved)。两页均为静态 HTML，共用 `www.iana.org`。2026-11-18 从 Codex 启动的 WSL `cc` 和 Windows `deskmate-win` 均解析到 `198.18.1.67`。用户在平时启动桌面的 WSL 终端复核，也使用 `cc` 并得到同一地址。生产工具的地址校验拒绝该地址，阻塞于 GET 前。Windows 上确认 Clash Verge Rev 2.4.1 正在运行，运行配置启用了 TUN 和 `fake-ip`，当前 `blacklist` 过滤列表未匹配该域名。[R4 验证记录](verification.md#r4-真实网页验收前的-dns-诊断)

在将用于启动桌面的 WSL 终端，从项目根目录用同一个 `cc` 解释器执行 DNS 预检。该命令只解析 `www.iana.org`，不初始化 Provider：

```bash
cd /mnt/d/ldj/03/DeskMate && \
  . /home/ldj/anaconda3/etc/profile.d/conda.sh && conda activate cc && \
  PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 python - <<'PY'
import asyncio
import sys
from likecc.tools.fetch_web_page import resolve_host, public_ip

async def check():
    print('Python:', sys.executable)
    ips = await resolve_host('www.iana.org', 443)
    print('www.iana.org:', ', '.join(ips) or '无 DNS 地址')
    if not ips:
        raise SystemExit('DNS 预检拒绝：无 DNS 地址')
    for ip in ips:
        try:
            public_ip(ip)
        except ValueError as exc:
            raise SystemExit(f'DNS 预检拒绝：{ip}（{exc}）') from None
    print('DNS 预检通过：所有地址都通过公网检查')

asyncio.run(check())
PY
```

当前订阅的原脚本经核对是默认的 `main` 回传模板，已按原字节备份到本机用户临时目录。用户在 Clash Verge 的「订阅」页右键当前启用的订阅，打开「编辑脚本」并保存了以下内容。脚本将 `www.iana.org` 追加到已有 `dns.fake-ip-filter`，适用于当前 `blacklist` 模式。[Clash Verge 扩展脚本说明](https://www.clashverge.dev/guide/extend.html) · [Mihomo DNS 过滤说明](https://wiki.metacubex.one/en/config/dns/#fake-ip-filter)

```javascript
function main(config, profileName) {
  const dns = config.dns;
  const domain = "www.iana.org";
  if (dns && dns["enhanced-mode"] === "fake-ip" &&
      (dns["fake-ip-filter-mode"] ?? "blacklist") === "blacklist" &&
      Array.isArray(dns["fake-ip-filter"]) && !dns["fake-ip-filter"].includes(domain)) {
    dns["fake-ip-filter"].push(domain);
  }
  return config;
}
```

保存后核对运行配置的过滤列表含一条 `www.iana.org` 和原有的 24 条其他项。用上述命令复测，WSL `cc` 返回的两个 IPv4 和两个 IPv6 全部通过公网校验。作用范围是启用该订阅时该域名的 DNS 响应，两份样例都覆盖。需要恢复时，将备份的原脚本粘回同一编辑器、保存并复测。

正常会话中的资料模式对两条显式 URL 分别发出权限请求，探针逐条批准，生产 `FetchWebPage` 实际读取两页。两次均为 HTTPS 200 直达，来源记录、正文长度、TLS 主机名和正常关闭均核对通过。探针只脚本化模型工具调用，使用生产 DNS 和真实 HTTPX 传输。[无模型实网结果](verification.md#r4-无模型实网检查)

独立公开样例工作区已准备在 `/mnt/d/ldj/03/DeskMate/.r1-verification/r4-public-pvrwgaf4`。其中 `project_notes.md` SHA256 为 `23f6d302affcc181428f7ccac9f7a3dc37fc78b838b01ba88dcbebeccd753988`，目标 `outputs/project-summary.md` 初始不存在。工作区提供一个空密钥的 `deepseek-r4` 模板，使用 DeepSeek Anthropic 兼容地址和 `deepseek-flash`，另加规则拒绝覆盖示例笔记。

无模型网页检查通过后，用户已授权本轮单次真实 Provider 任务并接受实际用量计费。启动时在本机隐藏输入现有 Key：

```bash
(
    set +x
    cd /mnt/d/ldj/03/DeskMate &&
        . /home/ldj/anaconda3/etc/profile.d/conda.sh && conda activate cc || exit 1
    r4_workspace=/mnt/d/ldj/03/DeskMate/.r1-verification/r4-public-pvrwgaf4
    IFS= read -r -s -p 'DeepSeek Key（输入不回显）: ' r4_key || exit 1
    printf '\n'
    [ -n "$r4_key" ] || { printf '%s\n' 'Key 为空，启动已取消。'; exit 1; }
    ANTHROPIC_API_KEY="$r4_key" env -u ANTHROPIC_AUTH_TOKEN -u QT_QPA_PLATFORM \
        python -m likecc.desktop --work-dir "$r4_workspace" --provider deepseek-r4
)
```

11 月 18 日完成单次真实资料任务。用户在可见窗口核对并批准两个 URL 与唯一写入路径，实际文件含三条来源，原笔记哈希与基线一致。成果回读比对通过，退出重开后原会话恢复，文件和工具记录均无变化。11 月 20 日用户继续完成权限等待时取消、同会话重用、新产物回读及退出恢复，日志和文件审计通过。[真实桌面验收记录](verification.md#r4-真实-provider-桌面验收)

## 连续验收清单（2026-11-20）

用户已连续操作并确认结果正常，下列步骤保留为验收记录。额外任务由用户在桌面手动发送，会产生 DeepSeek 用量，准备阶段估计约 6–9 轮请求，实际计费未查询。网页、笔记和既有成果沿用本轮独立样例工作区。新增产物为 `outputs/cancel-retry-summary.md`，编写清单时该路径不存在，执行后已有验收产物。

1. 在真实资料模式、`deepseek-r4 / deepseek-flash` 和原样例工作区中点击「新建会话」，记录新会话 ID。聊天区应为空、状态就绪。后续三次任务使用同一新会话。

2. 发送以下只读任务。出现对应 `FetchWebPage` 权限卡片后，点击卡片的「取消运行」。预期运行以 `cancelled` 结束、卡片消失、回到就绪、输入和发送可用。源文件和成果文件应无变化。权限默认等待 300 秒，操作应在该时间内完成。

```text
请用 FetchWebPage 读取 https://www.iana.org/help/example-domains 一次，读取成功后用一句中文概括页面。文件操作范围为空。
```

3. 在同一会话再次发送上面的任务。权限卡片出现后点击「本次允许」，卡片消失后立即点底部「取消当前请求」。预期仍可回到就绪，卡片清空。IANA 响应较快，若取消时工具结果已显示「已读」，只能记录取消发生在后续执行阶段；若已 completed，记录未捕捉到取消窗口。每种情况记录一次即可。仅凭窗口的执行中状态不足以证明取消发生在 HTTP 响应流读取期间，实网流内取消仍须结合实际事件或保持待覆盖。

4. 同一会话发送下面的恢复任务。核对并批准单个网页和唯一目标写入。预期两项来源成功、只写一次新文件、实际 ReadFile 回读、成果为「已回读核对」、运行 completed、回到就绪。来源编号按本轮实际返回值使用。

```text
请重新读取当前工作区的 project_notes.md，以及 https://www.iana.org/help/example-domains，各读取一次。
两份资料读取成功后，写一份简短中文摘要到 outputs/cancel-retry-summary.md，包含笔记中的目标和下一步，以及网页对示例域名用途的说明，正文标注本轮工具返回的来源编号，来源清单交给写入工具追加。
本次唯一可写路径是 outputs/cancel-retry-summary.md，只写入一次。权限确认通过工具调用触发的桌面卡片处理。写完用 ReadFile 实际回读，再报告完成。如果读取失败，请报告原因并结束任务。
```

5. 在另一个 WSL 终端执行以下文件检查及恢复前快照。需要保持这个终端开着，后面的比较使用其中的变量。检查失败时保留输出并停止后续任务。

```bash
cd /mnt/d/ldj/03/DeskMate/.r1-verification/r4-public-pvrwgaf4 &&
sha256sum -c <<'HASHES'
23f6d302affcc181428f7ccac9f7a3dc37fc78b838b01ba88dcbebeccd753988  project_notes.md
3c2ed274eb8518c6077392eef65fef4026fbbb288fcf7a5282683e0106a4725a  outputs/project-summary.md
HASHES
if [ "$?" -eq 0 ] && [ -s outputs/cancel-retry-summary.md ]; then
    r4_check_files=(project_notes.md outputs/project-summary.md outputs/cancel-retry-summary.md .likecc/sessions/*.jsonl)
    r4_before_restore=$(mktemp /tmp/deskmate-r4-restore.XXXXXX)
    if {
        sha256sum -- "${r4_check_files[@]}" &&
        stat --printf='%n | %s | %y\n' -- "${r4_check_files[@]}"
    } > "$r4_before_restore"; then
        cat outputs/cancel-retry-summary.md
        printf '\n恢复前快照已保存：%s\n' "$r4_before_restore"
    fi
else
    printf '%s\n' '检查未通过，请保留输出并反馈。'
fi
```

预期两个原文件哈希检查均为 OK。新文件正文和本轮两条来源一致，来源账目只有一份。此文件检查验证实际产物，是否真正回读还需要前一步的工具记录。

6. 点击「退出应用」，启动窗口的原终端返回后立即运行 `printf '退出码=%s\n' "$?"`。预期为 0。用本文启动命令重开相同工作区，在会话下拉框选择第 1 步记录的新 ID，点击「恢复所选会话」。预期恢复取消和成功任务的历史、保持就绪、没有新权限卡片。来源/成果面板可按当前运行清空。

7. 在第 5 步保留的检查终端中执行以下比较。预期输出「验收通过」。文件列表固定于恢复前，新启动产生的空白会话文件不参与比较。

```bash
diff -u "$r4_before_restore" <(
    sha256sum -- "${r4_check_files[@]}" &&
    stat --printf='%n | %s | %y\n' -- "${r4_check_files[@]}"
) && printf '%s\n' '验收通过：恢复前后内容、大小和修改时间均一致。'
```

8. 最后点击「退出应用」，在启动终端再次打印退出码。统一反馈新会话 ID、两次取消的实际阶段、成功任务的成果标签、两个退出码和文件比较结果。恢复前后截图或报错内容可用于定位差异。

执行结果为首轮权限等待取消、第二轮正常完成、第三轮成功写入和回读。第 3 步未捕捉到实际取消窗口，HTTP 流内取消保留为未覆盖项。实网重定向仍未覆盖，现有两份 IANA 样例为 HTTPS 直达，逐跳校验已有离线测试。退出恢复前后 7 个文件的哈希、大小及修改时间已独立核对一致。[收尾结果与覆盖边界](verification.md#r4-收尾结论与覆盖边界)
