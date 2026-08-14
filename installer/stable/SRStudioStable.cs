using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("SR Studio Stable")]
[assembly: System.Reflection.AssemblyProduct("SR Studio")]
[assembly: System.Reflection.AssemblyCompany("SR")]
[assembly: System.Reflection.AssemblyDescription("Acesso universal ao canal Stable do SR Studio")]
[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
[assembly: System.Reflection.AssemblyFileVersion("1.0.0.0")]

namespace SRStudioStable
{
    internal static class Program
    {
        internal const string RepoBase = "https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/main";
        internal const string BootstrapUrl = RepoBase + "/launcher/files/SRStudioBootstrap.ps1";
        internal const string StableManifestUrl = RepoBase + "/stable/manifest.json";
        internal const string LauncherManifestUrl = RepoBase + "/manifests/launcher.json";

        [STAThread]
        private static int Main(string[] args)
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            if (args != null && args.Length > 0 && (args[0] == "/selftest" || args[0] == "--selftest"))
                return StableBootstrap.SelfTest();

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new StableForm());
            return 0;
        }
    }

    internal static class StableBootstrap
    {
        internal static readonly string Root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SRStudio");
        internal static readonly string LauncherDir = Path.Combine(Root, "Launcher");
        internal static readonly string ConfigDir = Path.Combine(Root, "Config");
        internal static readonly string LogsDir = Path.Combine(Root, "Logs");
        internal static readonly string BootstrapPath = Path.Combine(LauncherDir, "SRStudioBootstrap.ps1");
        internal static readonly string ConfigPath = Path.Combine(ConfigDir, "launcher.json");
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

        internal static void Prepare()
        {
            Directory.CreateDirectory(Root);
            Directory.CreateDirectory(LauncherDir);
            Directory.CreateDirectory(ConfigDir);
            Directory.CreateDirectory(LogsDir);
        }

        internal static string ReadLatestStableLabel()
        {
            string text = DownloadString(Program.StableManifestUrl);
            var obj = Json.DeserializeObject(text) as Dictionary<string, object>;
            if (obj == null) return "Stable atual";
            string label = GetString(obj, "release_label");
            string version = GetString(obj, "version");
            if (!String.IsNullOrWhiteSpace(label)) return label + (String.IsNullOrWhiteSpace(version) ? "" : " • " + version);
            return String.IsNullOrWhiteSpace(version) ? "Stable atual" : version;
        }

        internal static void DownloadCurrentBootstrap()
        {
            Prepare();
            string temp = BootstrapPath + ".download";
            if (File.Exists(temp)) File.Delete(temp);
            using (WebClient wc = NewClient())
                wc.DownloadFile(Program.BootstrapUrl + "?t=" + DateTimeOffset.UtcNow.ToUnixTimeSeconds(), temp);
            if (!File.Exists(temp) || new FileInfo(temp).Length < 1000)
                throw new Exception("Bootstrap oficial baixado está inválido.");
            if (File.Exists(BootstrapPath)) File.Delete(BootstrapPath);
            File.Move(temp, BootstrapPath);
        }

        internal static void SetStableChannel()
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
            cfg["channel"] = "stable";
            cfg["auto_update"] = true;
            cfg["repair_on_start"] = true;
            cfg["allow_offline"] = true;
            cfg["remote_manifest_base"] = Program.RepoBase;
            cfg["entrypoint"] = "SR_Studio_Gerador.py";
            cfg["download_timeout_seconds"] = 600;
            cfg["download_retries"] = 3;
            cfg["auto_update_launcher"] = true;
            File.WriteAllText(ConfigPath, Json.Serialize(cfg), new UTF8Encoding(false));
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
                string stable = DownloadString(Program.StableManifestUrl);
                string launcher = DownloadString(Program.LauncherManifestUrl);
                if (String.IsNullOrWhiteSpace(stable) || String.IsNullOrWhiteSpace(launcher)) return 2;
                return 0;
            }
            catch { return 1; }
        }

        private static string DownloadString(string url)
        {
            using (WebClient wc = NewClient())
                return wc.DownloadString(url + (url.Contains("?") ? "&" : "?") + "t=" + DateTimeOffset.UtcNow.ToUnixTimeSeconds());
        }

        private static WebClient NewClient()
        {
            WebClient wc = new WebClient();
            wc.Encoding = Encoding.UTF8;
            wc.Headers[HttpRequestHeader.UserAgent] = "SRStudioStable/1.0";
            wc.Headers[HttpRequestHeader.CacheControl] = "no-cache";
            return wc;
        }

        private static string GetString(Dictionary<string, object> d, string key)
        {
            object v;
            return d != null && d.TryGetValue(key, out v) && v != null ? Convert.ToString(v) : "";
        }
    }

    internal sealed class StableForm : Form
    {
        private Label status;
        private Label version;
        private ProgressBar progress;

        internal StableForm()
        {
            Text = "SR Studio — Stable";
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            MinimizeBox = false;
            ClientSize = new Size(520, 245);
            BackColor = Color.FromArgb(246, 249, 253);
            Font = new Font("Segoe UI", 9F);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

            Panel header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 88;
            header.BackColor = Color.FromArgb(24, 67, 180);
            Controls.Add(header);

            Label title = new Label();
            title.Text = "SR Studio — Canal Stable";
            title.ForeColor = Color.White;
            title.Font = new Font("Segoe UI Semibold", 18F, FontStyle.Bold);
            title.AutoSize = true;
            title.Location = new Point(28, 18);
            header.Controls.Add(title);

            Label subtitle = new Label();
            subtitle.Text = "Versão oficial com atualização automática";
            subtitle.ForeColor = Color.FromArgb(220, 232, 255);
            subtitle.AutoSize = true;
            subtitle.Location = new Point(31, 57);
            header.Controls.Add(subtitle);

            version = new Label();
            version.Text = "Consultando Stable mais recente...";
            version.Font = new Font("Segoe UI Semibold", 10F, FontStyle.Bold);
            version.ForeColor = Color.FromArgb(24, 67, 180);
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
            note.Text = "Este executável sempre abre a versão Stable oficial mais recente.";
            note.ForeColor = Color.FromArgb(90, 100, 110);
            note.Location = new Point(28, 211);
            note.Size = new Size(464, 24);
            Controls.Add(note);

            Shown += async delegate { await StartStableAsync(); };
        }

        private async Task StartStableAsync()
        {
            try
            {
                string stable = await Task.Run<string>(delegate { return StableBootstrap.ReadLatestStableLabel(); });
                version.Text = "Stable disponível: " + stable;
                status.Text = "Atualizando Bootstrap oficial...";
                await Task.Run(delegate { StableBootstrap.DownloadCurrentBootstrap(); });
                status.Text = "Ativando canal Stable...";
                await Task.Run(delegate { StableBootstrap.SetStableChannel(); });
                status.Text = "Atualizando Launcher e SR Studio...";
                int code = await Task.Run<int>(delegate { return StableBootstrap.RunBootstrap(); });
                if (code != 0)
                    throw new Exception("O Launcher retornou o código " + code + ".\n\nLog: " + Path.Combine(StableBootstrap.LogsDir, "launcher.log"));
                Close();
            }
            catch (Exception ex)
            {
                progress.Style = ProgressBarStyle.Blocks;
                progress.Value = 0;
                status.Text = "Não foi possível abrir o canal Stable.";
                MessageBox.Show(ex.Message, "SR Studio Stable", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}
