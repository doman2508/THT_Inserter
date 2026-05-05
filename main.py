import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import pandas as pd
import json
import shutil
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageTk
import os
from bs4 import BeautifulSoup
import re  # Dodane
import tkinter.font as tkFont

# Utwórz główne okno aplikacji
root = tk.Tk()
root.title("MSX THT INSERTER V0.21")

# Tworzenie ramek dla różnych sekcji interfejsu
input_frame = tk.Frame(root)
input_frame.grid(row=0, column=0, sticky='nsew')

button_frame = tk.Frame(root)
button_frame.grid(row=1, column=0, sticky='ew')

table_frame = tk.Frame(root)
table_frame.grid(row=2, column=0, sticky='nsew')

font_style = tkFont.Font(family="Arial", size=16, weight="bold")
# Konfiguracja rozmiarów kolumn i wierszy, aby ramki mogły się rozszerzać
root.columnconfigure(0, weight=1)
root.rowconfigure(2, weight=1)

# Zmienne globalne
result_table = None
component_data_list = None
image_width = None
image_height = None
project_data = {}
treeview = None

# Dodane zmienne globalne
image_label = None  # To be initialized
image_thumbnail = None  # To store the thumbnail image

# Utwórz pola wejściowe i przyciski

# Nazwa projektu
tk.Label(input_frame, text="Nazwa projektu:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
project_name_entry = tk.Entry(input_frame)
project_name_entry.grid(row=0, column=1, padx=5, pady=5)

# Szerokość PCB
tk.Label(input_frame, text="Szerokość PCB:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
pcb_width_entry = tk.Entry(input_frame)
pcb_width_entry.grid(row=1, column=1, padx=5, pady=5)

# Wysokość PCB
tk.Label(input_frame, text="Wysokość PCB:").grid(row=2, column=0, sticky='e', padx=5, pady=5)
pcb_height_entry = tk.Entry(input_frame)
pcb_height_entry.grid(row=2, column=1, padx=5, pady=5)

# Plik BOM
tk.Label(input_frame, text="Plik BOM:").grid(row=3, column=0, sticky='e', padx=5, pady=5)
bom_file_entry = tk.Entry(input_frame)
bom_file_entry.grid(row=3, column=1, padx=5, pady=5)
tk.Button(input_frame, text="Wybierz...", command=lambda: select_bom_file()).grid(row=3, column=2, padx=5, pady=5)

# Plik P&P
tk.Label(input_frame, text="Plik P&P:").grid(row=4, column=0, sticky='e', padx=5, pady=5)
pp_file_entry = tk.Entry(input_frame)
pp_file_entry.grid(row=4, column=1, padx=5, pady=5)
tk.Button(input_frame, text="Wybierz...", command=lambda: select_pp_file()).grid(row=4, column=2, padx=5, pady=5)

# Obraz PCB
tk.Label(input_frame, text="Obraz PCB (PNG):").grid(row=5, column=0, sticky='e', padx=5, pady=5)
pcb_image_file_entry = tk.Entry(input_frame)
pcb_image_file_entry.grid(row=5, column=1, padx=5, pady=5)
tk.Button(input_frame, text="Wybierz...", command=lambda: select_pcb_image_file()).grid(row=5, column=2, padx=5, pady=5)

# Dodane: Utwórz widget image_label do wyświetlania miniatury obrazu
image_label = tk.Label(input_frame)
image_label.grid(row=0, column=3, rowspan=6, padx=5, pady=5)

# Funkcje wyboru plików
def select_bom_file():
    filepath = filedialog.askopenfilename(filetypes=[("Pliki Excel", "*.xlsx")])
    bom_file_entry.delete(0, tk.END)
    bom_file_entry.insert(0, filepath)

def select_pp_file():
    filepath = filedialog.askopenfilename(filetypes=[("Pliki Excel", "*.xlsx")])
    pp_file_entry.delete(0, tk.END)
    pp_file_entry.insert(0, filepath)

def select_pcb_image_file():
    filepath = filedialog.askopenfilename(filetypes=[("Pliki PNG", "*.png"), ("Pliki JPG", "*.jpg"), ("Pliki JPEG", "*.jpeg")])
    pcb_image_file_entry.delete(0, tk.END)
    pcb_image_file_entry.insert(0, filepath)
    load_and_display_image(filepath)

def load_and_display_image(filepath):
    global image_thumbnail  # to store the image
    if filepath:
        try:
            image = Image.open(filepath)
            # Tworzenie miniatury
            image.thumbnail((200, 200))  # Maksymalny rozmiar 200x200 pikseli
            image_thumbnail = ImageTk.PhotoImage(image)
            image_label.configure(image=image_thumbnail)
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się wczytać obrazu: {e}")

# Funkcja do wczytywania danych
def load_data():
    global result_table, component_data_list, image_width, image_height, project_data

    # Pobierz wartości z pól
    project_name = project_name_entry.get()
    pcb_width = pcb_width_entry.get()
    pcb_height = pcb_height_entry.get()
    bom_file = bom_file_entry.get()
    pp_file = pp_file_entry.get()
    pcb_image_file = pcb_image_file_entry.get()

    # Sprawdź, czy wszystkie pola są wypełnione
    if not all([project_name, pcb_width, pcb_height, bom_file, pp_file, pcb_image_file]):
        messagebox.showerror("Błąd", "Proszę wypełnić wszystkie pola i wybrać wszystkie pliki.")
        return

    # Walidacja szerokości i wysokości PCB
    try:
        pcb_width_value = float(pcb_width)
        pcb_height_value = float(pcb_height)
    except ValueError:
        messagebox.showerror("Błąd", "Szerokość i wysokość PCB muszą być liczbami.")
        return

    # Wczytaj pliki BOM i P&P
    try:
        bom_df = pd.read_excel(bom_file)
        pp_df = pd.read_excel(pp_file)
    except Exception as e:
        messagebox.showerror("Błąd", f"Błąd podczas wczytywania plików: {e}")
        return

    # Przetwarzanie danych
    try:
        # Rozgrupuj desygnatory w BOM
        bom_df['Desygnator'] = bom_df['Desygnator'].str.replace(' ', '')  # Usuń spacje
        bom_expanded = bom_df.assign(Desygnator=bom_df['Desygnator'].str.split(',')).explode('Desygnator')
        bom_expanded.reset_index(drop=True, inplace=True)

        # Upewnij się, że desygnatory są typu string i usuń spacje
        pp_df['Desygnator'] = pp_df['Desygnator'].astype(str).str.replace(' ', '')
        bom_expanded['Desygnator'] = bom_expanded['Desygnator'].astype(str).str.replace(' ', '')

        # Połącz dane z BOM i P&P na podstawie desygnatora
        merged_df = pd.merge(pp_df, bom_expanded, on='Desygnator', how='inner')

        # **Pierwsza struktura**: Każdy desygnator ma swoją linię z wartością i Indeksem Medcom
        first_structure = merged_df.copy()

        # **Druga struktura**: Tabela wynikowa zgrupowana według tej samej wartości
        # Grupowanie danych
        grouped = merged_df.groupby(['Wartość', 'Indeks Medcom'])

        # Utworzenie kolumny 'Desygnator' poprzez połączenie unikalnych desygnatorów
        result_table = grouped['Desygnator'].apply(lambda x: ','.join(sorted(x.unique(), key=alphanum_key))).reset_index()

        # Utworzenie kolumny 'Ilość' poprzez zliczenie elementów w każdej grupie
        result_table['Ilość'] = grouped.size().values

        # Upewnij się, że 'Ilość' jest typu całkowitego
        result_table['Ilość'] = result_table['Ilość'].astype(int)

        # Dodaj kolumny 'UWAGI' i 'Sekundy'
        result_table['UWAGI'] = ''
        result_table['Sekundy'] = ''

        # Przestaw kolumny w odpowiedniej kolejności
        result_table = result_table[['Desygnator', 'Wartość', 'Indeks Medcom', 'Ilość', 'UWAGI', 'Sekundy']]

        # Przygotuj component_data_list
        component_data = first_structure[['Desygnator', 'X', 'Y', 'Rotacja']].copy()

        # Funkcja do konwersji wartości z formatu "liczba mm" na float
        def convert_mm_to_float(value):
            if isinstance(value, str):
                value = value.replace(' ', '')  # Usuwamy spacje
                value = value.replace('mm', '')  # Usuwamy jednostkę 'mm'
                value = value.replace(',', '.')  # Zamieniamy przecinek na kropkę
                try:
                    return float(value)
                except ValueError:
                    return None
            else:
                return value

        # Zastosuj funkcję do kolumn 'X' i 'Y'
        component_data['X'] = component_data['X'].apply(convert_mm_to_float)
        component_data['Y'] = component_data['Y'].apply(convert_mm_to_float)

        # Usuń wiersze z niepoprawnymi danymi
        component_data = component_data.dropna(subset=['X', 'Y'])

        # Przekonwertuj dane komponentów do listy słowników
        component_data_list = component_data.to_dict(orient='records')

        # Wczytaj obraz, aby uzyskać jego rozmiar w pikselach
        with Image.open(pcb_image_file) as img:
            image_width, image_height = img.size

        # Zapisz dane projektu
        project_data = {
            'project_name': project_name,
            'pcb_width': pcb_width_value,
            'pcb_height': pcb_height_value,
            'pcb_image_file': pcb_image_file,
            'bom_file': bom_file,
            'pp_file': pp_file
        }

        # Wyświetl tabelę
        display_table()

        # Załaduj i wyświetl obraz
        load_and_display_image(pcb_image_file)

    except Exception as e:
        messagebox.showerror("Błąd", f"Błąd podczas przetwarzania danych: {e}")
        return

def alphanum_key(desig):
    """Funkcja zwraca klucz do sortowania alfanumerycznego."""
    match = re.match(r"([A-Za-z]+)(\d+)", desig)
    if match:
        return match.group(1), int(match.group(2))
    else:
        return desig, 0

# Funkcja obrotu o 90 stopni
def rotate_pcb():
    global pcb_width_entry, pcb_height_entry, component_data_list, project_data, pcb_image_file_entry

    # Obróć obraz o 90 stopni
    try:
        pcb_image_file = pcb_image_file_entry.get()
        if not pcb_image_file:
            messagebox.showerror("Błąd", "Nie wybrano pliku obrazu PCB.")
            return

        # Wczytaj obraz
        img = Image.open(pcb_image_file)

        # Obróć obraz o 90 stopni
        rotated_img = img.rotate(-90, expand=True)

        # Zapisz obrócony obraz w tym samym miejscu (lub zaktualizuj ścieżkę)
        rotated_img.save(pcb_image_file)

        # Zamień szerokość i wysokość PCB
        width = float(pcb_width_entry.get())
        height = float(pcb_height_entry.get())
        pcb_width_entry.delete(0, tk.END)
        pcb_width_entry.insert(0, str(height))
        pcb_height_entry.delete(0, tk.END)
        pcb_height_entry.insert(0, str(width))

        # Aktualizuj dane projektu
        project_data['pcb_width'], project_data['pcb_height'] = height, width

        # Przelicz współrzędne komponentów
        for component in component_data_list:
            x = component['X']
            y = component['Y']
            # Nowe współrzędne po obrocie
            component['X'] = y
            component['Y'] = width - x

        # Załaduj i wyświetl obrócony obraz
        load_and_display_image(pcb_image_file)

        messagebox.showinfo("Sukces", "Obraz PCB został obrócony o 90 stopni, a współrzędne zostały zaktualizowane.")

    except Exception as e:
        messagebox.showerror("Błąd", f"Nie udało się obrócić obrazu PCB: {e}")
        return

# Funkcja do wyświetlenia tabeli
def display_table():
    global treeview

    # Jeśli treeview już istnieje, usuń go
    if treeview:
        treeview.destroy()

    # Utwórz widget Treeview z kolumnami
    treeview = ttk.Treeview(table_frame, columns=('Lp.', 'Desygnator', 'Wartość',
                                                  'Indeks Medcom', 'Ilość', 'UWAGI', 'Sekundy'), show='headings')

    # Definiuj nagłówki kolumn
    treeview.heading('Lp.', text='Lp.')
    treeview.heading('Desygnator', text='Desygnator')
    treeview.heading('Wartość', text='Wartość')
    treeview.heading('Indeks Medcom', text='Indeks Medcom')
    treeview.heading('Ilość', text='Ilość')
    treeview.heading('UWAGI', text='UWAGI')
    treeview.heading('Sekundy', text='Sekundy na komponent')

    # Ustaw szerokość kolumn
    treeview.column('Lp.', width=30)
    treeview.column('Desygnator', width=150)
    treeview.column('Wartość', width=100)
    treeview.column('Indeks Medcom', width=100)
    treeview.column('Ilość', width=50)
    treeview.column('UWAGI', width=200)
    treeview.column('Sekundy', width=120)

    # Umożliw edycję kolumn 'UWAGI' i 'Sekundy'
    treeview.bind('<Double-1>', on_double_click)

    # Wstaw dane do treeview
    for index, row in result_table.iterrows():
        lp = index + 1  # Numeracja zaczyna się od 1
        treeview.insert('', 'end', values=(lp, row['Desygnator'], row['Wartość'],
                                           row['Indeks Medcom'], row['Ilość'], row['UWAGI'], row['Sekundy']))

    # Umieść treeview i scrollbar w table_frame
    treeview.grid(row=0, column=0, sticky='nsew')
    scrollbar = tk.Scrollbar(table_frame, orient='vertical', command=treeview.yview)
    treeview.configure(yscroll=scrollbar.set)
    scrollbar.grid(row=0, column=1, sticky='ns')

    table_frame.columnconfigure(0, weight=1)
    table_frame.rowconfigure(0, weight=1)

    # Ramka na przyciski tabeli
    buttons_frame = tk.Frame(table_frame)
    buttons_frame.grid(row=1, column=0, columnspan=2, pady=10)

    # Dodaj przyciski do zmiany kolejności wierszy
    move_up_button = tk.Button(buttons_frame, text="Przesuń w górę", command=move_row_up)
    move_up_button.pack(side='left', padx=10)

    move_down_button = tk.Button(buttons_frame, text="Przesuń w dół", command=move_row_down)
    move_down_button.pack(side='left', padx=10)

# Funkcja do edycji komórek po dwukrotnym kliknięciu
def on_double_click(event):
    item = treeview.identify_row(event.y)
    column = treeview.identify_column(event.x)
    if column in ('#6', '#7'):  # Kolumny 'UWAGI' i 'Sekundy' po dodaniu 'Lp.'
        x, y, width, height = treeview.bbox(item, column)
        value = treeview.set(item, column)

        # Utwórz nowe okno edycji
        edit_window = tk.Toplevel()
        edit_window.overrideredirect(True)
        edit_window.geometry(f"{width}x{height}+{treeview.winfo_rootx() + x}+{treeview.winfo_rooty() + y}")
        entry = tk.Entry(edit_window)
        entry.insert(0, value)
        entry.focus_set()
        entry.pack()

        def save_edit(event):
            new_value = entry.get()
            treeview.set(item, column, new_value)
            edit_window.destroy()

        entry.bind('<Return>', save_edit)
        entry.bind('<FocusOut>', lambda event: edit_window.destroy())

# Funkcja do przesuwania wiersza w górę
def move_row_up():
    selected_items = treeview.selection()
    for item in selected_items:
        index = treeview.index(item)
        if index > 0:
            treeview.move(item, '', index - 1)

# Funkcja do przesuwania wiersza w dół
def move_row_down():
    selected_items = treeview.selection()
    for item in reversed(selected_items):
        index = treeview.index(item)
        treeview.move(item, '', index + 1)

# Funkcja do generowania pliku HTML
def generate_html():
    # Pobierz aktualne wartości z pól wejściowych
    project_data['project_name'] = project_name_entry.get()
    project_data['pcb_width'] = float(pcb_width_entry.get())
    project_data['pcb_height'] = float(pcb_height_entry.get())
    project_data['pcb_image_file'] = pcb_image_file_entry.get()

    # Pobierz zmodyfikowane dane z treeview
    table_data = []
    for child in treeview.get_children():
        values = treeview.item(child)['values']
        row_data = {
            'Lp.': values[0],
            'Desygnator': values[1],
            'Wartość': values[2],
            'Indeks Medcom': values[3],
            'Ilość': values[4],
            'UWAGI': values[5],
            'Sekundy': values[6]
        }
        table_data.append(row_data)

    # Przygotuj dane do renderowania szablonu
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('pcb_template.html')

    # Konwertuj dane do formatu JSON
    table_data_json = json.dumps(table_data)
    component_data_json = json.dumps(component_data_list)

    # Uzyskaj nazwę pliku obrazu PCB bez ścieżki
    pcb_image_filename = os.path.basename(project_data['pcb_image_file'])

    # Kopiuj obraz PCB do folderu z plikiem HTML (jeśli to konieczne)
    output_folder = os.path.dirname(os.path.abspath(f"{project_data['project_name']}.html"))
    destination_image_path = os.path.join(output_folder, pcb_image_filename)
    if not os.path.exists(destination_image_path):
        try:
            shutil.copy(project_data['pcb_image_file'], destination_image_path)
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się skopiować obrazu PCB: {e}")
            return

    # Renderuj szablon
    output_html = template.render(
        pcb_image=pcb_image_filename,  # Używamy tylko nazwy pliku
        table_data=table_data_json,
        component_data=component_data_json,
        pcb_width=project_data['pcb_width'],
        pcb_height=project_data['pcb_height'],
        project_name=project_data['project_name']
    )

    # Zapisz plik HTML z aktualną nazwą projektu
    output_html_file = f"{project_data['project_name']}.html"
    with open(output_html_file, 'w', encoding='utf-8') as f:
        f.write(output_html)

    messagebox.showinfo("Sukces", f"Plik HTML został wygenerowany jako {output_html_file}")

# Funkcja wczytywania projektu z HTML
def load_project():
    global result_table, component_data_list, image_width, image_height, project_data

    filepath = filedialog.askopenfilename(filetypes=[("Pliki HTML", "*.html")])
    if not filepath:
        return

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Parsuj plik HTML
        soup = BeautifulSoup(html_content, 'html.parser')

        # Znajdź skrypty zawierające dane
        scripts = soup.find_all('script')

        # Inicjalizacja zmiennych
        table_data_json = None
        component_data_json = None

        # Szukaj zmiennych JavaScript z danymi
        for script in scripts:
            if script.string:
                script_content = script.string

                # Wyciągnij tableData
                match = re.search(r'var tableData = (.*?);', script_content, re.DOTALL)
                if match:
                    table_data_json = match.group(1)

                # Wyciągnij componentData
                match = re.search(r'var componentData = (.*?);', script_content, re.DOTALL)
                if match:
                    component_data_json = match.group(1)

                # Wyciągnij pcbWidth
                match = re.search(r'var pcbWidth = (.*?);', script_content)
                if match:
                    pcb_width_value = float(match.group(1))

                # Wyciągnij pcbHeight
                match = re.search(r'var pcbHeight = (.*?);', script_content)
                if match:
                    pcb_height_value = float(match.group(1))

                # Wyciągnij pcbImage
                match = re.search(r'var pcbImage = "(.*?)";', script_content)
                if match:
                    pcb_image_file = match.group(1)

        # Sprawdź, czy udało się wyciągnąć dane
        if not all([table_data_json, component_data_json]):
            messagebox.showerror("Błąd", "Nie udało się wyciągnąć danych z pliku HTML.")
            return

        # Konwertuj dane z JSON do struktur Pythona
        table_data = json.loads(table_data_json)
        component_data_list = json.loads(component_data_json)

        # Przygotuj result_table
        result_table = pd.DataFrame(table_data)

        # Aktualizuj dane projektu
        project_data = {
            'project_name': os.path.splitext(os.path.basename(filepath))[0],
            'pcb_width': pcb_width_value,
            'pcb_height': pcb_height_value,
            'pcb_image_file': pcb_image_file if 'pcb_image_file' in locals() else '',
            'bom_file': '',
            'pp_file': ''
        }

        # Zaktualizuj pola wejściowe
        project_name_entry.delete(0, tk.END)
        project_name_entry.insert(0, project_data['project_name'])

        pcb_width_entry.delete(0, tk.END)
        pcb_width_entry.insert(0, str(project_data['pcb_width']))

        pcb_height_entry.delete(0, tk.END)
        pcb_height_entry.insert(0, str(project_data['pcb_height']))

        pcb_image_file_entry.delete(0, tk.END)
        pcb_image_file_entry.insert(0, project_data['pcb_image_file'])

        # Jeśli obraz PCB nie został wyciągnięty, poproś użytkownika o jego wskazanie
        if not project_data['pcb_image_file']:
            messagebox.showinfo("Informacja", "Proszę wybrać plik obrazu PCB.")
            select_pcb_image_file()
        else:
            # Załaduj i wyświetl obraz
            load_and_display_image(project_data['pcb_image_file'])

        # Wyświetl tabelę
        display_table()

    except Exception as e:
        messagebox.showerror("Błąd", f"Błąd podczas wczytywania projektu: {e}")

# Przycisk Wczytaj dane
tk.Button(button_frame, text="Wczytaj dane (PP, BOM, PNG)", command=load_data).grid(row=0, column=0, padx=5, pady=10)

# Przycisk "Wczytaj istniejący projekt w HTML"
tk.Button(button_frame, text="Wczytaj istniejący projekt w HTML", command=load_project).grid(row=0, column=1, padx=5, pady=10)

# Przycisk Obrót o 90 stopni
tk.Button(button_frame, text="Obrót o 90 stopni", command=rotate_pcb).grid(row=0, column=2, padx=5, pady=10)

# Przycisk GENERUJ
tk.Button(button_frame, text="GENERUJ HTML", command=generate_html, font=font_style).grid(row=0, column=3, padx=5, pady=10)

# Uruchom główną pętlę aplikacji
root.mainloop()
