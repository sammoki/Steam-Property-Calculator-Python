import tkinter as tk
from tkinter import ttk
from iapws import IAPWS97
import matplotlib.pyplot as plt
from tkinter import filedialog
from reportlab.pdfgen import canvas
from tkinter import messagebox
import numpy as np

TOL = 1e-6
last_result = None 

def detect_phase(state):
    
    # دمای اشباع از روی فشار
    try:
        T_sat = IAPWS97(P=state.P, x=0).T
    except:
        return "Error"

    tol = 1e-3
    x = getattr(state, "x", None)

    # ------------------------------
    # 1) مادون‌سرد (Subcooled Liquid)
    # ------------------------------
    if state.T < T_sat - tol:
        return "Compressed Liquid"

    # ------------------------------
    # 2) سوپرهیت
    # ------------------------------
    if state.T > T_sat + tol:
        return "Superheated Steam"

    # ------------------------------
    # 3) دقیقا روی اشباع (T ≈ T_sat)
    # ------------------------------
    if abs(state.T - T_sat) <= tol:

        # حالت‌هایی که x موجود نیست
        if x is None:
            return "Saturated State"

        # ------------------------------
        # 3-1) مایع اشباع
        # ------------------------------
        if abs(x - 0) < 1e-6:
            return "Saturated Liquid"

        # ------------------------------
        # 3-2) بخار اشباع
        # ------------------------------
        if abs(x - 1) < 1e-6:
            return "Saturated Vapor"

        # ------------------------------
        # 3-3) دو فاز
        # ------------------------------
        if 0 < x < 1:
            return "Two-Phase (Wet Steam)"

        return "Saturated State"

    # اگر به اینجا برسیم یعنی یک حالت غیرمنتظره
    return "Unknown"


def mix(x, yf, yg):
    return yf + x * (yg - yf)

def calc_props(mode, a, b):

    try:
        # -------- P & T --------
        if mode == 1:
            state = IAPWS97(P=a/1000, T=b+273.15)

        # -------- P & x --------
        elif mode == 2:
            P = a/1000
            x = b
            if not (0 <= x <= 1):
                return "Quality must be between 0 and 1"

            sat_l = IAPWS97(P=P, x=0)
            sat_v = IAPWS97(P=P, x=1)

            class S:
                pass

            state = S()
            state.P, state.T, state.x = P, sat_l.T, x
            state.v = mix(x, sat_l.v, sat_v.v)
            state.h = mix(x, sat_l.h, sat_v.h)
            state.s = mix(x, sat_l.s, sat_v.s)
            state.u = mix(x, sat_l.u, sat_v.u)

        # -------- T & x --------
        elif mode == 3:
            T = a + 273.15
            x = b
            if not (0 <= x <= 1):
                return "Quality must be between 0 and 1"

            sat_l = IAPWS97(T=T, x=0)
            sat_v = IAPWS97(T=T, x=1)

            class S:
                pass

            state = S()
            state.P, state.T, state.x = sat_l.P, T, x
            state.v = mix(x, sat_l.v, sat_v.v)
            state.h = mix(x, sat_l.h, sat_v.h)
            state.s = mix(x, sat_l.s, sat_v.s)
            state.u = mix(x, sat_l.u, sat_v.u)

        # -------- P & v --------
        elif mode == 4:
            P = a/1000
            v = b
            sat_l = IAPWS97(P=P, x=0)
            sat_v = IAPWS97(P=P, x=1)
            vf, vg = sat_l.v, sat_v.v

            # شامل نقاط دقیق vf و vg
            if vf <= v <= vg:
                x = (v - vf) / (vg - vf)

                class S:
                    pass

                state = S()
                state.P, state.T, state.x, state.v = P, sat_l.T, x, v
                state.h = mix(x, sat_l.h, sat_v.h)
                state.s = mix(x, sat_l.s, sat_v.s)
                state.u = mix(x, sat_l.u, sat_v.u)
            else:
                # خارج دو فاز → به IAPWS می‌دهیم
                state = IAPWS97(P=P, v=v)

        # -------- P & h --------
        elif mode == 5:
            state = IAPWS97(P=a/1000, h=b)

        # -------- P & s --------
        elif mode == 6:
            state = IAPWS97(P=a/1000, s=b)

        # -------- T & s --------
        elif mode == 7:
            T = a + 273.15
            s_in = b

            # ابتدا اشباع را از روی دما می‌گیریم
            try:
                sat_l = IAPWS97(T=T, x=0)   # مایع اشباع
                sat_v = IAPWS97(T=T, x=1)   # بخار اشباع
            except:
                return "Temperature is out of saturation table valid range."

            sf, sg = sat_l.s, sat_v.s

            # ---- ناحیه دو فاز ----
            if sf <= s_in <= sg:
                x = (s_in - sf) / (sg - sf)

                class S: pass
                state = S()
                state.T = T
                state.P = sat_l.P
                state.x = x
                state.s = s_in
                state.v = mix(x, sat_l.v, sat_v.v)
                state.h = mix(x, sat_l.h, sat_v.h)
                state.u = mix(x, sat_l.u, sat_v.u)

            # ---- مایع فشرده ----
            elif s_in < sf:
                # فشار را از اشباع می‌گیریم، حل پایدار
                P = sat_l.P
                state = IAPWS97(T=T, P=P)

            # ---- بخار سوپرهیت ----
            elif s_in > sg:
                P = sat_v.P
                state = IAPWS97(T=T, P=P)

            else:
                return "Unexpected error in T & s mode."


        # ---------- Phase detection ----------
        phase_str = detect_phase(state)

        # ---------- Saturated properties if 0 < x < 1 ----------
        sat_data = None
        if getattr(state, "x", None) is not None and 0 < state.x < 1:
            sat_l = IAPWS97(P=state.P, x=0)
            sat_v = IAPWS97(P=state.P, x=1)
            sat_data = {
                "vf": sat_l.v,
                "vg": sat_v.v,
                "vfg": sat_v.v - sat_l.v,
                "hf": sat_l.h,
                "hg": sat_v.h,
                "hfg": sat_v.h - sat_l.h,
                "sf": sat_l.s,
                "sg": sat_v.s,
                "sfg": sat_v.s - sat_l.s,
                "uf": sat_l.u,
                "ug": sat_v.u,
                "ufg": sat_v.u - sat_l.u,
            }

        # ---------- Safe numeric output ----------
        return {
            "T": state.T - 273.15,      # °C
            "P": state.P * 1000,        # kPa
            "v": state.v,               # m³/kg
            "h": state.h,               # kJ/kg
            "s": state.s,               # kJ/kg·K
            "u": state.u,               # kJ/kg
            "x": getattr(state, "x", None),
            "phase": phase_str,
            "sat": sat_data
        }

    except Exception as e:
        return f"Calculation error inside calc_props:\n{e}"

# ----------------- PDF Export -----------------
def export_pdf():
    file_path = filedialog.asksaveasfilename(
        defaultextension=".pdf",
        filetypes=[("PDF file","*.pdf")]
    )

    if not file_path:
        return
    c = canvas.Canvas(file_path)
    text = output.get("1.0","end")
    y = 800

    for line in text.split("\n"):
        c.drawString(50, y, line)
        y -= 20
    c.save()

# ----------------- Plots -----------------
def generate_saturation_curve():
    T_celsius = np.linspace(0.01, 373.0, 300)   # تعداد نقاط بیشتر = دقت بالاتر
    T_kelvin = T_celsius + 273.15

    s_sat_l, s_sat_v, h_sat_l, h_sat_v, valid_T = [], [], [], [], []
    for T in T_kelvin:
        try:
            sat_l = IAPWS97(T=T, x=0)
            sat_v = IAPWS97(T=T, x=1)
            valid_T.append(T - 273.15)
            s_sat_l.append(sat_l.s)
            s_sat_v.append(sat_v.s)
            h_sat_l.append(sat_l.h)
            h_sat_v.append(sat_v.h)
        except:
            continue

    return {
        "T_sat": valid_T,
        "s_sat_l": s_sat_l,
        "s_sat_v": s_sat_v,
        "h_sat_l": h_sat_l,
        "h_sat_v": h_sat_v,
    }

def zoom_factory(ax, base_scale=1.2):
    def zoom(event):
        # فقط وقتی که ماوس داخل این محور باشد عمل می‌کند
        if event.inaxes != ax:
            return
        cur_xlim = ax.get_xlim()
        cur_ylim = ax.get_ylim()
        xdata = event.xdata
        ydata = event.ydata
        if xdata is None or ydata is None:
            return

        if event.button == 'up':
            scale_factor = 1 / base_scale
        elif event.button == 'down':
            scale_factor = base_scale
        else:
            return

        new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
        new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor
        # نسبت فاصله از لبه‌های فعلی
        relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
        rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])

        ax.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * relx])
        ax.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * rely])
        ax.figure.canvas.draw_idle()
    return zoom

#Plots

#ts_plot
def plot_ts_point(result):
    s = result["s"]
    T = result["T"]

    
    # تولید منحنی اشباع
    sat_data = generate_saturation_curve()
    
    fig, ax = plt.subplots(figsize=(9, 6))
    fig.canvas.manager.set_window_title("T-s Diagram")
    fig.canvas.mpl_connect('scroll_event', zoom_factory(ax, base_scale=1.5))

    ax.set_facecolor("#1e1e1e")
    fig.patch.set_facecolor("#1e1e1e")
    ax.tick_params(colors='white')

    # پس‌زمینه
    ax.set_facecolor("#1e1e1e")
    fig.patch.set_facecolor("#1e1e1e")
    ax.tick_params(colors='white')
    ax.grid(True, linestyle="--", alpha=0.3, color='gray')
    
    # رسم منحنی اشباع
    ax.plot(sat_data["s_sat_l"], sat_data["T_sat"], 'b-', linewidth=2, label='Saturated Liquid Line')
    ax.plot(sat_data["s_sat_v"], sat_data["T_sat"], 'r-', linewidth=2, label='Saturated Vapor Line')
    
    # پر کردن ناحیه دو فاز
    ax.fill_betweenx(sat_data["T_sat"], sat_data["s_sat_l"], sat_data["s_sat_v"], 
                     alpha=0.2, color='yellow', label='Two-Phase Region')
    # نقطه اصلی
    ax.scatter(s, T, color="#00ffaa", s=120, zorder=5, edgecolors="black", label="State Point")

    # خطوط راهنما
    ax.axvline(x=s, color="#00ffaa", linestyle="--", linewidth=1.2, alpha=0.8)
    ax.axhline(y=T, color="#00ffaa", linestyle="--", linewidth=1.2, alpha=0.8)

    # متن کنار نقطه
    ax.annotate(
        f"({s:.4f}, {T:.2f})",
        xy=(s, T),
        xytext=(10, 10),
        textcoords="offset points",
        fontsize=10,
        color="black",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.9)
    )

    ax.set_title("Temperature - Entropy (T-s) Diagram", fontsize=14, fontweight="bold", color='white')
    ax.set_xlabel("Entropy, s (kJ/kg·K)", fontsize=12 , color='white')
    ax.set_ylabel("Temperature, T (°C)", fontsize=12, color='white')

    ax.grid(True, linestyle="--", alpha=0.5 )
    ax.legend()
    plt.tight_layout()
    plt.show()
#HS plot
def plot_hs_point(result):
    s = result["s"]
    h = result["h"]

    # تولید منحنی اشباع
    sat_data = generate_saturation_curve()
    
    fig, ax = plt.subplots(figsize=(9, 6))
    fig.canvas.manager.set_window_title("h-s Diagram")
    fig.canvas.mpl_connect('scroll_event', zoom_factory(ax, base_scale=1.2))

    ax.set_facecolor("#1e1e1e")
    fig.patch.set_facecolor("#1e1e1e")
    ax.tick_params(colors='white')
    
    # پس‌زمینه
    ax.set_facecolor("#1e1e1e")
    fig.patch.set_facecolor("#1e1e1e")
    ax.tick_params(colors='white')
    ax.grid(True, linestyle="--", alpha=0.3, color='gray')
    
    # رسم منحنی اشباع
    ax.plot(sat_data["s_sat_l"], sat_data["h_sat_l"], 'b-', linewidth=2, label='Saturated Liquid Line')
    ax.plot(sat_data["s_sat_v"], sat_data["h_sat_v"], 'r-', linewidth=2, label='Saturated Vapor Line')
    
    # پر کردن ناحیه دو فاز
    ax.fill_betweenx(sat_data["T_sat"], sat_data["s_sat_l"], sat_data["s_sat_v"], 
                     alpha=0.2, color='yellow', label='Two-Phase Region')
    
    # نقطه اصلی
    ax.scatter(s, h, color="#00ffaa", s=120, zorder=5, edgecolors="black", label="State Point")

    # خطوط راهنما
    ax.axvline(x=s, color="#00ffaa", linestyle="--", linewidth=1.2, alpha=0.8)
    ax.axhline(y=h, color="#00ffaa", linestyle="--", linewidth=1.2, alpha=0.8)

    # متن کنار نقطه
    ax.annotate(
        f"({s:.4f}, {h:.2f})",
        xy=(s, h),
        xytext=(10, 10),
        textcoords="offset points",
        fontsize=10,
        color="black",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.9)
    )

    ax.set_title("Enthalpy - Entropy (h-s) Diagram", fontsize=14, fontweight="bold", color='white')
    ax.set_xlabel("Entropy, s (kJ/kg·K)", fontsize=12, color='white')
    ax.set_ylabel("Enthalpy, h (kJ/kg)", fontsize=12, color='white')

    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend()
    plt.tight_layout()
    plt.show()


#Help
def show_help():
    
    help_window = tk.Toplevel(root)
    help_window.title("📖 راهنمای کامل برنامه")
    help_window.geometry("800x600")
    help_window.configure(bg="#1e1e1e")
    help_window.resizable(True, True)
    
    notebook = ttk.Notebook(help_window)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)
    
    style = ttk.Style()
    style.configure("TNotebook", background="#1e1e1e")
    style.configure("TNotebook.Tab", background="#2d2d2d", foreground="white", padding=[10, 5])
    style.map("TNotebook.Tab", background=[("selected", "#47a8ff")])
    
    # -------- تابع کمکی برای ساخت یک Text راست‌چین بدون فوکوس --------
    def create_help_text(parent, text_content):
        scroll = tk.Scrollbar(parent)
        scroll.pack(side="right", fill="y")
        
        text_widget = tk.Text(
            parent,
            wrap="word",
            yscrollcommand=scroll.set,
            font=("Tahoma", 11),
            bg="#1e1e1e",
            fg="white",
            padx=15,
            pady=15,
            highlightthickness=0,   # حذف کادر فوکوس
            takefocus=0,            # عدم دریافت فوکوس با Tab
            borderwidth=0,          # حذف هرگونه حاشیه
            insertwidth=0           # پنهان کردن نشانگر تایپ
        )
        text_widget.pack(fill="both", expand=True)
        scroll.config(command=text_widget.yview)
        
        # جلوگیری کامل از فوکوس حتی با کلیک
        text_widget.bind("<FocusIn>", lambda e: "break")
        text_widget.bind("<Button-1>", lambda e: "break")
        
        text_widget.insert("1.0", text_content)
        # اعمال راست‌چین‌سازی با تگ
        text_widget.tag_configure("right", justify='right')
        text_widget.tag_add("right", "1.0", "end")
        text_widget.config(state="disabled")
        
        return text_widget
    
    # ----------------- تب ۱: مقدمه -----------------
    intro_frame = tk.Frame(notebook, bg="#1e1e1e")
    notebook.add(intro_frame, text="📋مقدمه")
    
    intro_text = """
     Steam Property Calculator🔬
    
خواص ترمودینامیکی آب/بخار را محاسبه می‌کند IAPWS-97 این برنامه با استفاده از استاندارد 
    
    :قابلیت‌های اصلی ⚙️
    محاسبه دقیق خواص آب و بخار در ۷ حالت مختلف ورودی
    تشخیص خودکار فاز (مایع مادون‌سرد، دو فاز، بخار سوپرهیت و ...)
    با نقطه حالت محاسبه شده T-s و h-s نمایش نمودارهای  
    PDF خروجی‌گیری به فرمت

    :IAPWS-97 استاندارد 📊
    انجمن بین‌المللی خواص آب و بخار
    فرمول‌های دقیق برای محاسبه خواص ترمودینامیکی آب و بخار
    """
    create_help_text(intro_frame, intro_text)
    
    # ----------------- تب ۲: حالت‌های ورودی -----------------
    input_frame = tk.Frame(notebook, bg="#1e1e1e")
    notebook.add(input_frame, text="📥حالت‌های ورودی")
    
    input_text = """
    🎯هفت حالت مختلف برای تعیین وضعیت ترمودینامیکی    
    P & T (فشار و دما)
       مثال: P=101.325 kPa, T=100°C → آب در بخار داغ
       ۸۰۰°C:برای بخار سوپرهیت می‌توانید دما را تا این مقدار بررسی کنید      
    
    
    P & x (فشار و کیفیت) 
       x=0 → مایع اشباع
       x=1 → بخار اشباع
       0<x<1 → مخلوط دو فاز
       در این حالت حداکثر دما ۳۷۳.۹۵ درجه سلسیوس (دمای بحرانی) خواهد بود.
       مثال: P=500 kPa, x=0.8 → مخلوط با ۸۰٪ بخار
    
    T & x (دما و کیفیت)
       در این حالت حداکثر دما ۳۷۳.۹۵ درجه سلسیوس (دمای بحرانی) خواهد بود
       مثال: T=150°C, x=0.5
    
    P & v (فشار و حجم مخصوص)
       
    P & h (فشار و آنتالپی)
       مثال: P=2000 kPa, h=2800 kJ/kg → بخار سوپرهیت
    
    P & s (فشار و آنتروپی)
       مثال: P=500 kPa, s=6.5 kJ/kg·K
    
    T & s (دما و آنتروپی)
       مثال: T=300°C, s=7.0 kJ/kg·K
    
    :نکات مهم⚠️
    کیفیت فقط برای ناحیه دو فاز (بین ۰ و ۱) معنا دارد.
    برای حالت‌های 
    P & T، P & h، P & s و T & s
    در ناحیه بخار سوپرهیت، دما می‌تواند تا ۸۰۰ درجه سلسیوس بالا برود.
    فشار باید بین ۰.۶۱۱  و ۲۲۰۶۴  باشد (نقاط سه‌گانه و بحرانی) واحد کیلوپاسکال.
    حداقل دمای مجاز برای کلیه حالت‌ها ۰.۰۱ درجه سلسیوس (نقطه سه‌گانه) است.
    """
    create_help_text(input_frame, input_text)
    
    # ----------------- تب ۳: واحدها -----------------
    units_frame = tk.Frame(notebook, bg="#1e1e1e")
    notebook.add(units_frame, text="📏واحدها")
    
    units_data = [
        ["فشار", "P", "کیلوپاسکال", "kPa"],
        ["دما", "T", "درجه سلسیوس", "°C"],
        ["حجم مخصوص", "v", "مترمکعب بر کیلوگرم", "m³/kg"],
        ["آنتالپی", "h", "کیلوژول بر کیلوگرم", "kJ/kg"],
        ["انرژی داخلی", "u", "کیلوژول بر کیلوگرم", "kJ/kg"],
        ["آنتروپی", "s", "کیلوژول بر کیلوگرم-کلوین", "kJ/kg·K"],
        ["کیفیت", "x", "بدون واحد", "-"]
    ]
    
    units_canvas = tk.Canvas(units_frame, bg="#1e1e1e", highlightthickness=0)
    units_scroll = tk.Scrollbar(units_frame, orient="vertical", command=units_canvas.yview)
    units_scrollable_frame = tk.Frame(units_canvas, bg="#1e1e1e")
    
    units_scrollable_frame.bind(
        "<Configure>",
        lambda e: units_canvas.configure(scrollregion=units_canvas.bbox("all"))
    )
    
    units_canvas.create_window((0, 0), window=units_scrollable_frame, anchor="nw")
    units_canvas.configure(yscrollcommand=units_scroll.set)
    
    headers = ["مقدار", "نماد", "واحد", "نماد واحد"]
    for col, header in enumerate(headers):
        tk.Label(
            units_scrollable_frame,
            text=header,
            font=("Tahoma", 11, "bold"),
            bg="#1a946b",
            fg="white",
            padx=10,
            pady=8
        ).grid(row=0, column=col, sticky="ew", padx=2, pady=2)
    
    for row, unit in enumerate(units_data, 1):
        for col, value in enumerate(unit):
            bg_color = "#2d2d2d" if row % 2 == 0 else "#3d3d3d"
            tk.Label(
                units_scrollable_frame,
                text=value,
                font=("Tahoma", 10),
                bg=bg_color,
                fg="white",
                padx=10,
                pady=6
            ).grid(row=row, column=col, sticky="ew", padx=2, pady=1)
    
    units_canvas.pack(side="left", fill="both", expand=True)
    units_scroll.pack(side="right", fill="y")
    
    # ----------------- تب ۴: نمودارها -----------------
    diagrams_frame = tk.Frame(notebook, bg="#1e1e1e")
    notebook.add(diagrams_frame, text="📈 نمودارها")
    
    diagrams_text = """
    :نمودارهای قابل نمایش📊 
    
    1 (T-s) نمودار دما-آنتروپی  
       • محور افقی: آنتروپی (s) → kJ/kg·K
       • محور عمودی: دما (T) → °C
       • ویژگی‌ها:
         - نمایش خطوط مایع اشباع (آبی) و بخار اشباع (قرمز)
         - ناحیه دو فاز (زرد رنگ)
         - نقطه وضعیت محاسبه شده (سبز رنگ)
         - خطوط راهنمای نقطه
         - قابلیت زوم با اسکرول ماوس
    
    2 (h-s) نمودار آنتالپی-آنتروپی
       • محور افقی: آنتروپی (s) → kJ/kg·K
       • محور عمودی: آنتالپی (h) → kJ/kg
       • ویژگی‌ها:
         - نمایش خطوط مایع اشباع (آبی) و بخار اشباع (قرمز)
         - ناحیه دو فاز (زرد رنگ)
         - نقطه وضعیت محاسبه شده (سبز رنگ)
         - خطوط راهنمای نقطه
         - قابلیت زوم با اسکرول ماوس
    
    :نحوه استفاده از نمودارها🎯
    ۱. ابتدا یک حالت ورودی را انتخاب کنید
    ۲.را بزنید Calculateمقادیر را وارد کرده و  
    ۳. یکی از نمودارها را انتخاب کنید Diagram از منوی 
    ۴. :در پنجره نمودار
       • با اسکرول ماوس زوم کنید
       • از نوار ابزار پایین نمودار برای ذخیره، بزرگنمایی و ... استفاده کنید
    
    : تفسیر نمودارها🔍
    • نقطه در سمت چپ خط مایع اشباع → مایع مادون‌سرد
    • نقطه در ناحیه زرد → مخلوط دو فاز
    • نقطه در سمت راست خط بخار اشباع → بخار سوپرهیت
    • نقطه روی خط مایع اشباع → مایع اشباع
    • نقطه روی خط بخار اشباع → بخار اشباع
    """
    create_help_text(diagrams_frame, diagrams_text)
    
    # ----------------- تب ۵: خروجی‌گیری -----------------
    export_frame = tk.Frame(notebook, bg="#1e1e1e")
    notebook.add(export_frame, text="💾 خروجی‌گیری")
    
    export_text = """
    :روش‌های خروجی‌گیری از نتایج💾 
        
    :PDFفرمت خروجی📄
    • شامل تمام خواص محاسبه شده
    • شامل فاز تشخیص داده شده
    • در صورت دو فاز بودن، خواص اشباع نیز نمایش داده می‌شود
    • تاریخ و زمان محاسبه
    • پارامترهای ورودی
    
    :ذخیره نمودارها🖼️
    • روی آیکون ذخیره (💾) در نوار ابزار کلیک کنید
    • فرمت دلخواه را انتخاب کنید
    """
    create_help_text(export_frame, export_text)
    
    # ----------------- تب ۶: نکات فنی -----------------
    tech_frame = tk.Frame(notebook, bg="#1e1e1e")
    notebook.add(tech_frame, text="⚙️ نکات فنی")
    
    tech_text = """
    :اطلاعات فنی و محدودیت‌ها⚙️
    
    :محدوده اعتبار محاسبات🔬
    • حداقل دما: ۰.۰۱ درجه سلسیوس (نقطه سه‌گانه آب) برای تمام نواحی.
    • برای ناحیه اشباع (دو فاز) و کیفیت بخار حداکثر دما ۳۷۳.۹۵ درجه سلسیوس (نقطه بحرانی).
    • برای بخار سوپرهیت (بدون کیفیت): می‌توانید دما را تا ۸۰۰  وارد کنید.
    
    :محدودیت‌ها⚠️
    • کیفیت  فقط در ناحیه دو فاز (۰ تا ۱) تعریف شده و دما را به زیر ۳۷۳.۹۵ درجه سانتی گراد محدود می‌کند.
    • برای آب خالص (بدون نمک و ناخالصی) طراحی شده است.
    • محاسبات در نزدیکی نقطه بحرانی ممکن است دقت کمتری داشته باشد.
    
    :دقت محاسبات🎯
    • دقت دما: ۰.۰۰۱°C ±
    • دقت فشار: ۰.۰۰۱ kPa ±
    • دقت آنتالپی: ۰.۰۰۱ kJ/kg ±
    • دقت آنتروپی: ۰.۰۰۰۱ kJ/kg·K ±
    
    :الگوریتم تشخیص فاز🔍
    ۱. محاسبه دمای اشباع از روی فشار
    ۲. مقایسه دمای ورودی با دمای اشباع
    ۳. :تشخیص ۵ حالت مختلف
       - مایع مادون‌سرد (Compressed Liquid)
       - مایع اشباع (Saturated Liquid)
       - مخلوط دو فاز (Two-Phase)
       - بخار اشباع (Saturated Vapor)
       - بخار سوپرهیت (Superheated Steam)
    
    :کتابخانه‌های استفاده شده📊
    • tkinter: رابط کاربری گرافیکی
    • iapws:  محاسبات ترمودینامیکی و داده های خواص
    • matplotlib: رسم نمودارها
    • numpy: محاسبات عددی
    • reportlab: PDFتولید فایل 
    
    :گزارش خطا🐞
    :در صورت بروز خطا
    ۱. مقادیر ورودی را بررسی کنید (فشار و دما داخل محدوده مجاز باشند).
    ۲. اگر با کیفیت  کار می‌کنید، دمای بالای 373.94 وارد نکنید.
    ۳. برای بخار سوپرهیت از حالت‌های 
    P & T، P & h، P & s و T & s
    .استفاده کنید
    ۴.در صورت مواجه شدن با خطای
    
        """
    create_help_text(tech_frame, tech_text)
    # ----------------- تب 7: انتقادات و پیشنهادات -----------------
    saeed_frame = tk.Frame(notebook, bg="#1e1e1e")
    notebook.add(saeed_frame, text="📝انتقادات و پیشنهادات")
    
    saeed_text = """
    هر ایده، انتقاد یا پیشنهادی که 
    برای بهتر شدن نرم افزار دارین رو
    لطفا با ما در میان بگذارید
    تا بتوانیم در نسخه‌های بعدی،
    بهبود بخشیم
    باتشکر



    
    

"""


    create_help_text(saeed_frame, saeed_text)

    copy_btn = ttk.Button(
    saeed_frame,
    text="کپی آیدی  , Telegram (@SAM_5718)",
    command=lambda: copy_to_clipboard("@Saeed_M713")
    )
    copy_btn.pack(pady=10)

    close_btn = ttk.Button(
        help_window,
        text="بستن راهنما",
        command=help_window.destroy,
        style="TButton"
    )

    close_btn.pack(pady=10)
    
    notebook.select(0)




def copy_to_clipboard(text):
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()  # برای اینکه کلیپ‌بورد پایدار بشه
    messagebox.showinfo("کپی شد", f"'{text}' در کلیپ‌بورد کپی شد.")
# =====================================
# === Modern Dark GUI Section (Smaller)
# =====================================
root = tk.Tk()
root.title("Steam Property Calculator (IAPWS97)")
root.geometry("720x560")   # کوچکتر شده
root.configure(bg="#1e1e1e")

# ttk Style
style = ttk.Style()
style.theme_use("clam")
style.configure("TLabel", background="#1e1e1e", foreground="white", font=("Segoe UI", 10))
style.configure("TButton", background="#2d89ef", foreground="white",
                font=("Segoe UI", 10, "bold"), padding=5)
style.map("TButton", background=[("active", "#1b62b4")])
style.configure("TEntry", fieldbackground="#2d2d2d", foreground="white")
style.configure("TCombobox", fieldbackground="#2d2d2d", background="#2d2d2d", foreground="white")

# Title
title_label = tk.Label(
    root,
    text=" Thermodynamics  Calculator 💧",
    font=("Segoe UI", 15, "bold"),
    bg="#1e1e1e",
    fg="#47a8ff",
)
title_label.pack(pady=10)

# Mode Selector
mode_label = tk.Label(root, text="Select Input Mode:", bg="#1e1e1e", fg="white", font=("Segoe UI", 10))
mode_label.pack()
mode_box = ttk.Combobox(
    root,
    values=[
        "1 - P & T",
        "2 - P & x",
        "3 - T & x",
        "4 - P & v",
        "5 - P & h",
        "6 - P & s",
        "7 - T & s",
    ],
    state="readonly",
    font=("Segoe UI", 10),
)
mode_box.pack(pady=5)

# Input Frame
frame = tk.Frame(root, bg="#1e1e1e")
frame.pack(pady=8)

label1 = ttk.Label(frame, text="Parameter 1:")
label1.grid(row=0, column=0, padx=8, pady=4, sticky="e")
val1 = ttk.Entry(frame, width=22)
val1.grid(row=0, column=1, padx=8, pady=4)

label2 = ttk.Label(frame, text="Parameter 2:")
label2.grid(row=1, column=0, padx=8, pady=4, sticky="e")
val2 = ttk.Entry(frame, width=22)
val2.grid(row=1, column=1, padx=8, pady=4)

def update_labels(event):
    labels = {
        "1": ("Pressure (kPa)", "Temperature (°C)"),
        "2": ("Pressure (kPa)", "Quality x"),
        "3": ("Temperature (°C)", "Quality x"),
        "4": ("Pressure (kPa)", "Specific Volume (m³/kg)"),
        "5": ("Pressure (kPa)", "Enthalpy (kJ/kg)"),
        "6": ("Pressure (kPa)", "Entropy (kJ/kg·K)"),
        "7": ("Temperature (°C)", "Entropy (kJ/kg·K)"),
    }
    choice = mode_box.get().split()[0] if mode_box.get() else ""
    if choice in labels:
        label1.config(text=labels[choice][0])
        label2.config(text=labels[choice][1])
    else:
        label1.config(text="Parameter 1:")
        label2.config(text="Parameter 2:")

mode_box.bind("<<ComboboxSelected>>", update_labels)

# Output Frame
output_frame = tk.LabelFrame(
    root, text=" Results ", bg="#1e1e1e", fg="white", font=("Segoe UI", 10, "bold")
)
output_frame.pack(pady=10)

output = tk.Text(
    output_frame,
    height=16,
    width=85,
    bg="#101010",
    fg="#00ffaa",
    insertbackground="#fafffd",
    font=("Consolas", 10),
)
output.pack(padx=8, pady=8)
# Buttons
btn_frame = tk.Frame(root, bg="#1e1e1e")
btn_frame.pack(pady=10)

def calculate():
    global last_result
    # چک اینکه مود انتخاب شده
    if not mode_box.get():
        result_text = "Please select an input mode."
        last_result = None 
    else:
        try:
            mode = int(mode_box.get().split()[0])
            a = float(val1.get())
            b = float(val2.get())
            result = calc_props(mode, a, b)

            # اگر رشته است، یعنی خطا
            if isinstance(result, str):
                result_text = f"Calculation error:\n{result}"
                last_result = None
            else:
                last_result = result
                # دیکشنری موفق
                lines = [
                    f"T = {result['T']:.4f} °C",
                    f"P = {result['P']:.4f} kPa",
                    f"v = {result['v']:.6f} m³/kg",
                    f"h = {result['h']:.4f} kJ/kg",
                    f"s = {result['s']:.6f} kJ/kg·K",
                    f"u = {result['u']:.4f} kJ/kg",
                    "",
                    f"Phase: {result['phase']}",
                ]

                # اگر دو فاز است، خواص اشباع را هم اضافه کن
                if result["sat"] is not None and result["x"] is not None and 0 < result["x"] < 1:
                    sat = result["sat"]
                    lines += [
                        "",
                        "--- Saturated Properties ---",
                        f"vf = {sat['vf']:.6f}",
                        f"vg = {sat['vg']:.6f}",
                        f"vfg = {sat['vfg']:.6f}",
                        f"hf = {sat['hf']:.4f}",
                        f"hg = {sat['hg']:.4f}",
                        f"hfg = {sat['hfg']:.4f}",
                        f"sf = {sat['sf']:.6f}",
                        f"sg = {sat['sg']:.6f}",
                        f"sfg = {sat['sfg']:.6f}",
                        f"uf = {sat['uf']:.4f}",
                        f"ug = {sat['ug']:.4f}",
                        f"ufg = {sat['ufg']:.4f}",
                        "",
                        f"Quality x = {result['x']:.6f}",
                    ]

                result_text = "\n".join(lines)

        except ValueError:
            result_text = "Input error:\nPlease enter numeric values for parameters."
        except Exception as e:
            result_text = f"Unexpected error in calculate():\n{e}"

    output.delete(1.0, tk.END)
    output.insert(tk.END, result_text)

ttk.Button(btn_frame, text="Calculate", width=15, command=calculate).grid(row=0, column=0, padx=8)
ttk.Button(btn_frame, text="Exit", width=15, command=root.destroy).grid(row=0, column=1, padx=8)

# Footer
footer = tk.Label(
    root,
    text="Using IAPWS97",
    bg="#1e1e1e",
    fg="#808080",
    font=("Segoe UI", 9),
)
footer.pack(side="bottom", pady=6)

# ======================
# Menu Bar
# ======================
menu_bar = tk.Menu(root)
# ---------- Output ----------
output_menu = tk.Menu(menu_bar, tearoff=0)
output_menu.add_command(label="Export PDF", command=export_pdf)
menu_bar.add_cascade(label="Output", menu=output_menu)

# ---------- Plot ----------
plot_menu = tk.Menu(menu_bar, tearoff=0)

def show_ts():
    if last_result:
        plot_ts_point(last_result)

def show_hs():
    if last_result:
        plot_hs_point(last_result)

plot_menu.add_command(label="T-s Diagram", command=show_ts)
plot_menu.add_command(label="h-s Diagram", command=show_hs)

menu_bar.add_cascade(label="Diagram", menu=plot_menu)

# ---------- Help ----------
help_menu = tk.Menu(menu_bar, tearoff=0)
help_menu.add_command(label="User Guide", command=show_help)
menu_bar.add_cascade(label="Help", menu=help_menu)

root.config(menu=menu_bar)
root.mainloop()
