using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("SR Studio Beta")]
[assembly: System.Reflection.AssemblyProduct("SR Studio")]
[assembly: System.Reflection.AssemblyCompany("SR")]
[assembly: System.Reflection.AssemblyDescription("Acesso universal resiliente ao canal Beta do SR Studio")]
[assembly: System.Reflection.AssemblyVersion("1.1.0.0")]
[assembly: System.Reflection.AssemblyFileVersion("1.1.0.0")]

namespace SRStudioBeta
{
    internal static class Program
    {
        internal const string RepoBase = "https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/main";
        internal const string BootstrapUrl = RepoBase + "/launcher/files/SRStudioBootstrap.ps1";
        internal const string BetaManifestUrl = RepoBase + "/beta/manifest.json";

        [STAThread]
        private static int Main(string[] args)
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            if (args != null && args.Length > 0 && (args[0] == "/selftest" || args[0] == "--selftest"))
                return BetaBootstrap.SelfTest();

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new BetaForm());
            return 0;
        }
    }

    internal static class BetaBootstrap
    {
        internal static readonly string Root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SRStudio");
        internal static readonly string LauncherDir = Path.Combine(Root, "Launcher");
        internal static readonly string ConfigDir = Path.Combine(Root, "Config");
        internal static readonly string CacheDir = Path.Combine(Root, "Cache");
        internal static readonly string LogsDir = Path.Combine(Root, "Logs");
        internal static readonly string BootstrapPath = Path.Combine(LauncherDir, "SRStudioBootstrap.ps1");
        internal static readonly string ConfigPath = Path.Combine(ConfigDir, "launcher.json");
        internal static readonly string BetaCachePath = Path.Combine(CacheDir, "beta_access_ui_manifest.json");
        internal static readonly string AccessLogPath = Path.Combine(LogsDir, "beta_access.log");
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

        internal static void Prepare()
        {
            Directory.CreateDirectory(Root);
            Directory.CreateDirectory(LauncherDir);
            Directory.CreateDirectory(ConfigDir);
            Directory.CreateDirectory(CacheDir);
            Directory.CreateDirectory(LogsDir);
        }

        internal static void Log(string message)
        {
            try
            {
                Prepare();
                File.AppendAllText(AccessLogPath, "[" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "] " + message + Environment.NewLine, Encoding.UTF8);
            }
            catch { }
        }

        internal static string ReadLatestBetaLabelSafe()
        {
            Prepare();
            string text = null;
            try
            {
                text = DownloadStringWithRetry(Program.BetaManifestUrl, 2);
                if (!String.IsNullOrWhiteSpace(text))
                    File.WriteAllText(BetaCachePath, text, new UTF8Encoding(false));
            }
            catch (Exception ex)
            {
                Log("Manifesto Beta online indisponível; usando cache. " + ex.Message);
                try { if (File.Exists(BetaCachePath)) text = File.ReadAllText(BetaCachePath, Encoding.UTF8); } catch { }
            }

            if (String.IsNullOrWhiteSpace(text)) return "Canal Beta";
            try
            {
                var obj = Json.DeserializeObject(text) as Dictionary<string, object>;
                if (obj == null) return "Canal Beta";
                string label = GetString(obj, "release_label");
                string version = GetString(obj, "version");
                if (!String.IsNullOrWhiteSpace(label)) return label + (String.IsNullOrWhiteSpace(version) ? "" : " • " + version);
                return String.IsNullOrWhiteSpace(version) ? "Canal Beta" : version;
            }
            catch { return "Canal Beta"; }
        }

        internal static void EnsureBootstrap()
        {
            Prepare();
            bool localValid = IsValidBootstrap(BootstrapPath);
            bool refreshDue = !localValid;
            try
            {
                if (localValid)
                    refreshDue = (DateTime.UtcNow - File.GetLastWriteTimeUtc(BootstrapPath)).TotalHours >= 6.0;
            }
            catch { refreshDue = !localValid; }

            if (!refreshDue)
            {
                Log("Bootstrap local válido reutilizado; nenhuma requisição necessária.");
                return;
            }

            string temp = BootstrapPath + ".download";
            try
            {
                if (File.Exists(temp)) File.Delete(temp);
                DownloadFileWithRetry(Program.BootstrapUrl, temp, 3);
                if (!IsValidBootstrap(temp)) throw new Exception("Bootstrap oficial baixado está inválido.");
                if (File.Exists(BootstrapPath)) File.Delete(BootstrapPath);
                File.Move(temp, BootstrapPath);
                Log("Bootstrap oficial atualizado.");
                return;
            }
            catch (Exception ex)
            {
                try { if (File.Exists(temp)) File.Delete(temp); } catch { }
                if (localValid)
                {
                    Log("Atualização do Bootstrap indisponível; reutilizando cópia local válida. " + ex.Message);
                    return;
                }
                throw new Exception("Não foi possível obter o Bootstrap e não existe cópia local válida. " + ex.Message, ex);
            }
        }

        internal static void SetBetaChannel()
        {
            Prepare();
            Dictionary<string, object> cfg = null;
            try
            {
                if (File.Exists(ConfigPath))
                    cfg = Json.DeserializeObject(File.ReadAllText(ConfigPath, Encoding.UTF8)) as Dictionary<string, object>;
            }
            catch { cfg = null; }

            if (cfg == null) cfg = new Dictionary<string, object>();
            cfg["schema"] = 3;
            cfg["channel"] = "beta";
            cfg["auto_update"] = true;
            cfg["repair_on_start"] = true;
            cfg["allow_offline"] = true;
            cfg["remote_manifest_base"] = Program.RepoBase;
            cfg["entrypoint"] = "SRStudio5/SR Studio 5.exe";
            cfg["download_timeout_seconds"] = 600;
            cfg["download_retries"] = 3;
            cfg["auto_update_launcher"] = true;

            string json = Json.Serialize(cfg);
            File.WriteAllText(ConfigPath, json, new UTF8Encoding(false));
        }

        internal static int RunBootstrap()
        {
            string ps = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), @"WindowsPowerShell\v1.0\powershell.exe");
            if (!File.Exists(ps)) ps = "powershell.exe";

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = ps;
            psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + BootstrapPath + "\"";
            psi.WorkingDirectory = LauncherDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.WindowStyle = ProcessWindowStyle.Hidden;

            Process p = Process.Start(psi);
            if (p == null) return 1;
            p.WaitForExit();
            return p.ExitCode;
        }

        internal static int SelfTest()
        {
            try
            {
                Prepare();
                if (String.IsNullOrWhiteSpace(Program.BootstrapUrl) || String.IsNullOrWhiteSpace(Program.BetaManifestUrl)) return 2;
                SetBetaChannel();
                return 0;
            }
            catch { return 1; }
        }

        private static bool IsValidBootstrap(string path)
        {
            try
            {
                if (!File.Exists(path) || new FileInfo(path).Length < 1000) return false;
                string head = File.ReadAllText(path, Encoding.UTF8);
                return head.IndexOf("SRStudio", StringComparison.OrdinalIgnoreCase) >= 0 || head.IndexOf("Launcher", StringComparison.OrdinalIgnoreCase) >= 0;
            }
            catch { return false; }
        }

        private static string DownloadStringWithRetry(string url, int retries)
        {
            Exception last = null;
            for (int attempt = 1; attempt <= retries; attempt++)
            {
                try
                {
                    using (WebClient wc = NewClient()) return wc.DownloadString(url);
                }
                catch (Exception ex)
                {
                    last = ex;
                    if (attempt < retries) Thread.Sleep(GetRetryDelayMs(ex, attempt));
                }
            }
            throw last ?? new Exception("Falha de rede.");
        }

        private static void DownloadFileWithRetry(string url, string destination, int retries)
        {
            Exception last = null;
            for (int attempt = 1; attempt <= retries; attempt++)
            {
                try
                {
                    using (WebClient wc = NewClient())
                    {
                        wc.DownloadFile(url, destination);
                        return;
                    }
                }
                catch (Exception ex)
                {
                    last = ex;
                    try { if (File.Exists(destination)) File.Delete(destination); } catch { }
                    if (attempt < retries) Thread.Sleep(GetRetryDelayMs(ex, attempt));
                }
            }
            throw last ?? new Exception("Falha de rede.");
        }

        private static int GetRetryDelayMs(Exception ex, int attempt)
        {
            int seconds = attempt == 1 ? 2 : (attempt == 2 ? 5 : 10);
            WebException web = ex as WebException;
            if (web != null)
            {
                HttpWebResponse response = web.Response as HttpWebResponse;
                if (response != null)
                {
                    string retryAfter = response.Headers["Retry-After"];
                    int parsed;
                    if (Int32.TryParse(retryAfter, out parsed) && parsed > 0)
                        seconds = Math.Min(60, parsed);
                    if ((int)response.StatusCode == 429)
                        Log("GitHub respondeu HTTP 429; aguardando " + seconds + "s antes de nova tentativa.");
                }
            }
            return seconds * 1000;
        }

        private static WebClient NewClient()
        {
            WebClient wc = new WebClient();
            wc.Encoding = Encoding.UTF8;
            wc.Headers[HttpRequestHeader.UserAgent] = "SRStudioBeta/1.1";
            wc.Headers[HttpRequestHeader.Accept] = "application/json,text/plain,*/*";
            return wc;
        }

        private static string GetString(Dictionary<string, object> d, string key)
        {
            object v;
            return d != null && d.TryGetValue(key, out v) && v != null ? Convert.ToString(v) : "";
        }
    }

    internal sealed class BetaForm : Form
    {
        private Label status;
        private Label version;
        private ProgressBar progress;

        internal BetaForm()
        {
            Text = "SR Studio — Beta";
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            MinimizeBox = false;
            ClientSize = new Size(520, 250);
            BackColor = Color.FromArgb(246, 249, 253);
            Font = new Font("Segoe UI", 9F);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

            Panel header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 88;
            header.BackColor = Color.FromArgb(0, 78, 146);
            Controls.Add(header);

            Label title = new Label();
            title.Text = "SR Studio — Canal Beta";
            title.ForeColor = Color.White;
            title.Font = new Font("Segoe UI Semibold", 18F, FontStyle.Bold);
            title.AutoSize = true;
            title.Location = new Point(28, 18);
            header.Controls.Add(title);

            Label subtitle = new Label();
            subtitle.Text = "Acesso e atualização automática";
            subtitle.ForeColor = Color.FromArgb(220, 236, 250);
            subtitle.AutoSize = true;
            subtitle.Location = new Point(31, 57);
            header.Controls.Add(subtitle);

            version = new Label();
            version.Text = "Consultando Beta mais recente...";
            version.Font = new Font("Segoe UI Semibold", 10F, FontStyle.Bold);
            version.ForeColor = Color.FromArgb(0, 78, 146);
            version.Location = new Point(28, 112);
            version.Size = new Size(464, 24);
            Controls.Add(version);

            status = new Label();
            status.Text = "Preparando...";
            status.Location = new Point(28, 145);
            status.Size = new Size(464, 24);
            Controls.Add(status);

            progress = new ProgressBar();
            progress.Location = new Point(28, 181);
            progress.Size = new Size(464, 18);
            progress.Style = ProgressBarStyle.Marquee;
            progress.MarqueeAnimationSpeed = 28;
            Controls.Add(progress);

            Label note = new Label();
            note.Text = "Falhas temporárias do GitHub não bloqueiam mais uma cópia local válida.";
            note.ForeColor = Color.FromArgb(90, 100, 110);
            note.Location = new Point(28, 211);
            note.Size = new Size(464, 24);
            Controls.Add(note);

            Shown += async delegate { await StartBetaAsync(); };
        }

        private async Task StartBetaAsync()
        {
            try
            {
                string beta = await Task.Run<string>(delegate { return BetaBootstrap.ReadLatestBetaLabelSafe(); });
                version.Text = "Beta disponível: " + beta;

                status.Text = "Verificando Bootstrap oficial...";
                await Task.Run(delegate { BetaBootstrap.EnsureBootstrap(); });

                status.Text = "Ativando canal Beta...";
                await Task.Run(delegate { BetaBootstrap.SetBetaChannel(); });

                status.Text = "Abrindo Launcher e verificando atualizações...";
                int code = await Task.Run<int>(delegate { return BetaBootstrap.RunBootstrap(); });
                if (code != 0)
                    throw new Exception("O Launcher retornou o código " + code + ".\n\nLog: " + Path.Combine(BetaBootstrap.LogsDir, "launcher.log"));

                Close();
            }
            catch (Exception ex)
            {
                progress.Style = ProgressBarStyle.Blocks;
                progress.Value = 0;
                status.Text = "Não foi possível abrir o canal Beta.";
                MessageBox.Show(ex.Message, "SR Studio Beta", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}
