import os
import re
import sys
from flask import Flask, render_template, request, jsonify
from threading import Thread
from pymongo import MongoClient
from groq import Groq
from supabase import create_client

url = "https://dxbyncqvkmifcvabhbey.supabase.co"
SUP_API_KEY = os.getenv("SUP_API_KEY")
supabase = create_client(url, SUP_API_KEY)

data = supabase.table("Wilgo_chapitres").select("*").eq("id_leçon", 1).execute()
print(data)

chapitres = data.data  # Ceci est une liste de dictionnaires

# Extraction des noms dans une liste
noms = [chapitre["nom"] for chapitre in chapitres]

print(noms)


# 🔐 Paramètre unique
SUJET_D_EXERCICE = noms[0]

# 🔐 MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["MaBD"]
messages_collection = db["testing"]

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
        """Charge la configuration depuis le fichier Markdown"""
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

            # Remplacement dynamique
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
        """Construit le prompt dynamique"""
        return f"""
{self.system}

{self.safety}

{self.assistant}

{conversation}
""".strip()

# 📦 Initialisation
prompt_manager = PromptManager()

app = Flask(__name__)

@app.route('/')
def home():
    messages_collection.delete_many({})
    return render_template('index.html', welcome_message=prompt_manager.welcome)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')

    if not user_message:
        return jsonify({"error": "Message vide"}), 400

    messages_collection.insert_one({"role": "User", "content": user_message})
    history = list(messages_collection.find({}, {"_id": 0}))

    try:
        chat_completion = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": prompt_manager.build_prompt(
                    "\n".join([f"{m['role']}: {m['content']}" for m in history])
                )}
            ],
            temperature=0.7,
            max_tokens=1024,
            top_p=1,
            stream=False
        )

        ai_response = chat_completion.choices[0].message.content

        messages_collection.insert_one({"role": "Assistant", "content": ai_response})

        return jsonify({"response": ai_response})

    except Exception as e:
        import traceback
        print("⚠️ ERREUR INTERNE :", traceback.format_exc())
        return jsonify({"error": "Erreur interne", "details": str(e)}), 500

# 🔄 Lancement spécial Jupyter
def run_flask():
    app.run(port=5000, debug=True, use_reloader=False)

Thread(target=run_flask).start()