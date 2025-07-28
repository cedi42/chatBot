import os
import re
import sys
from flask import Flask, render_template, request, jsonify
from threading import Thread
from groq import Groq
from supabase import create_client

# 🔗 Supabase
url = "https://dxbyncqvkmifcvabhbey.supabase.co"
SUP_API_KEY = os.getenv("SUP_API_KEY")
supabase = create_client(url, SUP_API_KEY)

# ✅ Valeur par défaut (sera remplacée dans /config)
SUJET_D_EXERCICE = "math"

# 🧠 Stockage en mémoire
conversation_history = [] # Liste pour stocker la conversation

# 🔐 Clé API Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

# 🧠 Gestionnaire de prompts
class PromptManager:
    def __init__(self, config_file="prompts.md"):
        self.config_file = config_file
        self.system = ""
        self.safety = ""
        self.assistant = ""
        self.welcome = ""
        self.load_config()

    def load_config(self):
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.system = re.search(r'#\sSystem(.?)##', content, re.DOTALL)
            self.safety = re.search(r'#\sSafety(.?)##', content, re.DOTALL)
            self.assistant = re.search(r'#\sAssistant(.?)##', content, re.DOTALL)
            self.welcome = re.search(r'#\sWelcome(.?)##', content, re.DOTALL)

            self.system = self._clean(self.system)
            self.safety = self._clean(self.safety)
            self.assistant = self._clean(self.assistant)
            self.welcome = self._clean(self.welcome)

            for attr in ['system', 'safety', 'assistant', 'welcome']:
                val = getattr(self, attr)
                val = val.replace('[SUJET_D_EXERCICE]', SUJET_D_EXERCICE)
                setattr(self, attr, val)

        except Exception as e:
            print(f"Erreur de chargement de la config: {e}")
            sys.exit(1)

    def _clean(self, match):
        return match.group(1).strip() if match else ""

    def build_prompt(self, conversation):
        return f"""
{self.system}

{self.safety}

{self.assistant}

{conversation}
""".strip()

# 📦 Initialisation
prompt_manager = PromptManager()
app = Flask(__name__)

# 🔧 Configuration temporaire
CONFIG_UTILISATEUR = {
    "classe": None,
    "matiere": None,
    "lecon": None
}

@app.route('/')
def home():
    conversation_history.clear()  # ❌ Vide la conversation à chaque (re)ouverture
    return render_template('index.html', welcome_message=prompt_manager.welcome)

@app.route('/config', methods=['POST'])
def config():
    classe = request.form.get("classe")
    matiere = request.form.get("matiere")
    lecon = request.form.get("lecon")

    if not (classe and matiere and lecon):
        return "Champs manquants", 400

    CONFIG_UTILISATEUR["classe"] = int(classe)
    CONFIG_UTILISATEUR["matiere"] = int(matiere)
    CONFIG_UTILISATEUR["lecon"] = int(lecon)

    data = supabase.table("Wilgo_chapitres") \
        .select("*") \
        .eq("id_lecon", CONFIG_UTILISATEUR["lecon"]) \
        .eq("id_matiere", CONFIG_UTILISATEUR["matiere"]) \
        .eq("id_niveau", CONFIG_UTILISATEUR["classe"]) \
        .execute()

    chapitres = data.data or []

    if not chapitres:
        return "Aucun chapitre trouvé.", 404

    noms = [chapitre["nom"] for chapitre in chapitres]

    global SUJET_D_EXERCICE
    SUJET_D_EXERCICE = noms[0]

    # 🔄 Recharger les prompts avec la nouvelle valeur
    prompt_manager.load_config()

    conversation_history.clear()  # ❌ Vide la conversation si on revalide les paramètres

    return render_template('index.html', welcome_message=prompt_manager.welcome)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')

    if not user_message:
        return jsonify({"error": "Message vide"}), 400

    # 🧠 Ajouter le message utilisateur
    conversation_history.append({"role": "User", "content": user_message})

    try:
        formatted_history = "\n".join([f"{m['role']}: {m['content']}" for m in conversation_history])

        chat_completion = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": prompt_manager.build_prompt(formatted_history)}
            ],
            temperature=0.7,
            max_tokens=1024,
            top_p=1,
            stream=False
        )

        ai_response = chat_completion.choices[0].message.content

        # 🧠 Ajouter la réponse de l'assistant
        conversation_history.append({"role": "Assistant", "content": ai_response})

        return jsonify({"response": ai_response})

    except Exception as e:
        import traceback
        print("⚠️ ERREUR INTERNE :", traceback.format_exc())
        return jsonify({"error": "Erreur interne", "details": str(e)}), 500

# 🔄 Lancement spécial Jupyter
def run_flask():
    app.run(port=5000, debug=True, use_reloader=False)

Thread(target=run_flask).start()