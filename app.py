import os
import re
import sys
from flask import Flask, render_template, request, jsonify
from groq import Groq
from supabase import create_client

# 🔗 Supabase
url = "https://dxbyncqvkmifcvabhbey.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR4YnluY3F2a21pZmN2YWJoYmV5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTMzMzc1MTYsImV4cCI6MjA2ODkxMzUxNn0.Eww30cCJ6NXRKWDGRK1Tr7Zr6pTb1O5O2gKSTdnfzpk"
supabase = create_client(url, key)

# ✅ Valeur par défaut (sera remplacée dans /config)
SUJET_D_EXERCICE = "général" # Changed default to something more generic

# 🧠 Stockage en mémoire
conversation_history = []  # Liste pour stocker la conversation

# 🔐 Clé API Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or "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"
groq_client = Groq(api_key=GROQ_API_KEY)

# 🧠 Gestionnaire de prompts
class PromptManager:
    def __init__(self, config_file="prompts.md"):
        self.config_file = config_file
        self.system = ""
        self.safety = ""
        self.assistant = ""
        self.welcome = ""
        # Don't load config here initially, as SUJET_D_EXERCICE might change
        # The load_config will be called when needed.

    def load_config(self, subject=None): # Added subject parameter
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.system = re.search(r'#\sSystem(.*?)##', content, re.DOTALL)
            self.safety = re.search(r'#\sSafety(.*?)##', content, re.DOTALL)
            self.assistant = re.search(r'#\sAssistant(.*?)##', content, re.DOTALL)
            self.welcome = re.search(r'#\sWelcome(.*?)##', content, re.DOTALL)

            self.system = self._clean(self.system)
            self.safety = self._clean(self.safety)
            self.assistant = self._clean(self.assistant)
            self.welcome = self._clean(self.welcome)

            # Use the passed subject or the global one
            current_subject = subject if subject else SUJET_D_EXERCICE

            for attr in ['system', 'safety', 'assistant', 'welcome']:
                val = getattr(self, attr)
                # Ensure the placeholder replacement happens correctly
                val = val.replace('[SUJET_D_EXERCICE]', current_subject)
                setattr(self, attr, val)

        except FileNotFoundError:
            print(f"Erreur: Le fichier de configuration '{self.config_file}' n'a pas été trouvé.")
            sys.exit(1)
        except Exception as e:
            print(f"Erreur de chargement de la config: {e}")
            sys.exit(1)

    def _clean(self, match):
        # Modified regex to be non-greedy (.*?) for better parsing
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
# Initial load of prompts with default subject
prompt_manager.load_config(SUJET_D_EXERCICE) # Load it here for the initial welcome message

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
    # Ensure welcome_message is up-to-date
    prompt_manager.load_config(SUJET_D_EXERCICE) # Re-load to ensure correct subject
    return render_template('index.html', welcome_message=prompt_manager.welcome)

@app.route('/config', methods=['POST'])
def config():
    global SUJET_D_EXERCICE # Declare global to modify
    classe = request.form.get("classe")
    matiere = request.form.get("matiere")
    lecon = request.form.get("lecon")

    if not (classe and matiere and lecon):
        # Render the template with an error message instead of a plain string
        return render_template('index.html', welcome_message=prompt_manager.welcome, error_message="Champs manquants. Veuillez remplir tous les champs.")

    try:
        CONFIG_UTILISATEUR["classe"] = int(classe)
        CONFIG_UTILISATEUR["matiere"] = int(matiere)
        CONFIG_UTILISATEUR["lecon"] = int(lecon)
    except ValueError:
        return render_template('index.html', welcome_message=prompt_manager.welcome, error_message="Veuillez entrer des nombres valides pour la classe, la matière et la leçon.")


    data = supabase.table("Wilgo_chapitres") \
        .select("*") \
        .eq("id_lecon", CONFIG_UTILISATEUR["lecon"]) \
        .eq("id_matiere", CONFIG_UTILISATEUR["matiere"]) \
        .eq("id_niveau", CONFIG_UTILISATEUR["classe"]) \
        .execute()

    chapitres = data.data or []

    if not chapitres:
        return render_template('index.html', welcome_message=prompt_manager.welcome, error_message="Aucun chapitre trouvé avec ces paramètres. Veuillez vérifier vos entrées.")

    noms = [chapitre["nom"] for chapitre in chapitres]

    SUJET_D_EXERCICE = noms[0] if noms else "général" # Fallback if no names found

    # 🔄 Recharger les prompts avec la nouvelle valeur
    prompt_manager.load_config(SUJET_D_EXERCICE)

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
        # The build_prompt method already takes care of the full prompt structure
        # You just need to pass the conversation history formatted as a string
        formatted_history = "\n".join([f"{m['role']}: {m['content']}" for m in conversation_history])
        
        # Pass the formatted history to build_prompt, which will integrate it with system, safety, assistant prompts
        full_prompt_content = prompt_manager.build_prompt(formatted_history)

        chat_completion = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": full_prompt_content} # Use the full prompt here
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

if __name__ == "__main__":
    app.run(port=5000, debug=True)