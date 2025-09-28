# Copyright S. Volkan Kücükbudak
# GPL3
import streamlit as st
import google.generativeai as genai
from google.generativeai import types
from PIL import Image
import io
import base64
import pandas as pd
import zipfile
import PyPDF2
import tempfile
import os
from streamlit_mic_recorder import mic_recorder
import json
import time

# Le prompt qui améliore considérablement la qualité de la transcription
transcription_prompt = """
Transcris le texte de cet audio avec la plus grande précision possible.
Contexte important : La langue parlée est très probablement le wolof, mais pourrait être du français.
L'audio peut contenir du bruit de fond ; fais de ton mieux pour isoler la voix principale et transcrire uniquement les paroles pertinentes.
Le résultat doit être la transcription brute, sans aucun texte ou formatage supplémentaire. Ne dis pas 'Voici la transcription :' ou quoi que ce soit d'autre.
"""

# Konfiguration der Seite
st.set_page_config(page_title="Gemini AI Chat Interface", page_icon=":gem:", layout="wide")

# Configurez l'API Gemini
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except KeyError:
    st.error("Google AI API Key non trouvé dans .streamlit/secrets.toml. Veuillez l'ajouter.")
    st.stop()
except Exception as e:
    st.error(f"Erreur lors de la configuration de l'API Key: {e}")
    st.stop()

# Initialisez le modèle Gemini
if "gemini_model" not in st.session_state:
    st.session_state.gemini_model = "gemini-2.5-flash"

model_instance = genai.GenerativeModel(st.session_state.gemini_model)

st.title("🤖 Gemini AI Chat Interface")
st.markdown("""
**Welcome to the Gemini AI Chat Interface!**
Chat seamlessly with Google's advanced Gemini AI models, supporting multiple input types.
🔗 [GitHub Profile](https://github.com/volkansah) | 
📂 [Project Repository](https://github.com/volkansah/gemini-ai-chat) | 
💬 [Soon](https://aicodecraft.io)
""")

# Prompt de transcription (from user's input)
TRANSCRIPTION_PROMPT = """
Transcris le texte de cet audio. La langue parlée est très probablement le wolof, mais pourrait être du français.
L'audio peut contenir du bruit de fond ; fais de ton mieux pour isoler la voix principale et transcrire uniquement les paroles pertinentes.
Ne fournis que la transcription brute, sans aucun texte ou formatage supplémentaire.
"""

# Prompt pour la synthèse vocale en Wolof
WOLOF_TTS_PROMPT = """
Prononce le texte suivant en Wolof, avec une intonation naturelle et claire.
"""

# Session State Management
if "messages" not in st.session_state:
    st.session_state.messages = []
if "uploaded_content" not in st.session_state:
    st.session_state.uploaded_content = None

# Funktionen zur Dateiverarbeitung
def encode_image(image):
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def process_file(uploaded_file):
    file_type = uploaded_file.name.split('.')[-1].lower()
    
    if file_type in ["jpg", "jpeg", "png"]:
        return {"type": "image", "content": Image.open(uploaded_file).convert('RGB')}
    
    code_extensions = ["html", "css", "php", "js", "py", "java", "c", "cpp"]
    if file_type in ["txt"] + code_extensions:
        return {"type": "text", "content": uploaded_file.read().decode("utf-8")}
    
    if file_type in ["csv", "xlsx"]:
        df = pd.read_csv(uploaded_file) if file_type == "csv" else pd.read_excel(uploaded_file)
        return {"type": "text", "content": df.to_string()}
    
    if file_type == "pdf":
        reader = PyPDF2.PdfReader(uploaded_file)
        return {"type": "text", "content": "".join(page.extract_text() for page in reader.pages if page.extract_text())}
    
    if file_type == "zip":
        with zipfile.ZipFile(uploaded_file) as z:
            newline = "\n"
            content = f"ZIP Contents:{newline}"
            
            text_extensions = ('.txt', '.csv', '.py', '.html', '.js', '.css', 
                              '.php', '.json', '.xml', '.c', '.cpp', '.java', 
                              '.cs', '.rb', '.go', '.ts', '.swift', '.kt', '.rs', '.sh', '.sql')
            
            for file_info in z.infolist():
                if not file_info.is_dir():
                    try:
                        with z.open(file_info.filename) as file:
                            if file_info.filename.lower().endswith(text_extensions):
                                file_content = file.read().decode('utf-8')
                                content += f"{newline}📄 {file_info.filename}:{newline}{file_content}{newline}"
                            else:
                                raw_content = file.read()
                                try:
                                    decoded_content = raw_content.decode('utf-8')
                                    content += f"{newline}📄 {file_info.filename} (unbekannte Erweiterung):{newline}{decoded_content}{newline}"
                                except UnicodeDecodeError:
                                    content += f"{newline}⚠️ Binärdatei ignoriert: {file_info.filename}{newline}"
                    except Exception as e:
                        content += f"{newline}❌ Erreur bei {file_info.filename}: {str(e)}{newline}"
            
            return {"type": "text", "content": content}
    
    return {"type": "error", "content": "Unsupported file format"}

def transcribe_audio_with_gemini(audio_file_path):
    try:
        audio_file = genai.upload_file(path=audio_file_path)
        transcription_model = genai.GenerativeModel('gemini-2.5-flash')
        response = transcription_model.generate_content([transcription_prompt, audio_file])
        return response.text.strip()
    except Exception as e:
        st.error(f"Erreur lors de la transcription audio: {e}")
        return None

# Funktionen zur Dateiverarbeitung
def process_knowledge_base_document(uploaded_file):
    file_type = uploaded_file.name.split('.')[-1].lower()
    if file_type == "pdf":
        reader = PyPDF2.PdfReader(uploaded_file)
        return "".join(page.extract_text() for page in reader.pages if page.extract_text())
    elif file_type == "txt":
        return uploaded_file.read().decode("utf-8")
    else:
        return "Unsupported file type for knowledge base."

# Sidebar für Einstellungen
with st.sidebar:
    st.subheader("Admin Panel")
    uploaded_kb_file = st.file_uploader("Upload Knowledge Base Document (PDF, TXT)", type=["pdf", "txt"], key="kb_uploader")

    if uploaded_kb_file is not None:
        file_path = os.path.join("knowledge_base_docs", uploaded_kb_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_kb_file.getbuffer())
        st.success(f"Fichier '{uploaded_kb_file.name}' téléchargé avec succès dans la base de connaissances.")
        
        # Process the uploaded knowledge base document
        extracted_text = process_knowledge_base_document(uploaded_kb_file)
        if extracted_text:
            st.session_state[f"kb_content_{uploaded_kb_file.name}"] = extracted_text
            st.info(f"Contenu du fichier '{uploaded_kb_file.name}' extrait et prêt à être indexé.")
        else:
            st.warning(f"Impossible d'extraire le contenu du fichier '{uploaded_kb_file.name}'.")

    st.subheader("Einstellungen")
    model_options = ["gemini-pro", "gemini-pro-vision", "gemini-2.5-flash"]
    
    if "gemini_model" not in st.session_state:
        st.session_state.gemini_model = "gemini-2.5-flash"

    model = st.sidebar.selectbox("Modell auswählen", model_options, index=model_options.index(st.session_state.gemini_model))
    st.session_state.gemini_model = model
    temperature = st.slider("Temperatur", 0.0, 1.0, 0.7, 0.01)
    max_tokens = st.slider("Max. Output-Token", 100, 4000, 1000, 10)
    system_prompt = st.text_area("System Prompt (Optional)", "")
    uploaded_image_file = st.file_uploader("Bild hochladen (Optional)", type=["png", "jpg", "jpeg"])
    uploaded_audio_file = st.file_uploader("Upload Audio File (Optional)", type=["mp3", "wav"])

# Datei-Upload
uploaded_file = st.file_uploader("Upload File (Image/Text/PDF/ZIP)", 
                               type=["jpg", "jpeg", "png", "txt", "pdf", "zip", 
                                     "csv", "xlsx", "html", "css", "php", "js", "py"])

if uploaded_file:
    processed = process_file(uploaded_file)
    st.session_state.uploaded_content = processed
    
    if processed["type"] == "image":
        st.image(processed["content"], caption="Uploaded Image", use_container_width=True)
    elif processed["type"] == "text":
        st.text_area("File Preview", processed["content"], height=200)

# Chat-Historie anzeigen
# Add custom CSS for the microphone button
st.markdown("""
<style>
.stMicRecorder {
    position: fixed;
    bottom: 16px;
    left: 50%; /* Centrer horizontalement */
    transform: translateX(-50%); /* Ajuster pour un centrage parfait */
    z-index: 1000;
    /* Vous pouvez ajouter d'autres styles ici pour le rendre plus grand ou plus visible */
}
.stChatInput {
    margin-left: 0 !important; /* Réinitialiser la marge si nécessaire */
    width: calc(100% - 80px); /* Ajuster la largeur pour laisser de l'espace au bouton */
    margin-bottom: 16px; /* Ajouter un peu d'espace en bas */
}
</style>
""", unsafe_allow_html=True)

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Add microphone button
audio_bytes = mic_recorder(start_prompt="▶️", stop_prompt="⏹️", just_once=True, key="mic_recorder")

# Add chat input
prompt_input = st.chat_input("Votre message...")

if audio_bytes:
    # Effacer le champ de saisie du chat pour afficher les résultats de l'audio
    # chat_input_container.empty()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        tmp_file.write(audio_bytes['bytes'])
        tmp_file_path = tmp_file.name
    
    st.session_state.audio_for_playback = audio_bytes['bytes']
    st.session_state.audio_file_path = tmp_file_path

    transcribed_text = transcribe_audio_with_gemini(tmp_file_path)
    # os.remove(tmp_file_path) # Supprimer le fichier temporaire après transcription
    
    if transcribed_text:
        st.session_state.transcribed_text = transcribed_text
        # Traduire en Wolof (supprimé car non souhaité pour l'input utilisateur)
        # try:
        #     translation_model = genai.GenerativeModel('gemini-2.5-flash')
        #     wolof_response = translation_model.generate_content([WOLOF_TRANSLATION_PROMPT + transcribed_text])
        #     st.session_state.wolof_translation = wolof_response.text.strip()
        # except Exception as e:
        #     st.error(f"Erreur lors de la traduction en Wolof: {e}")
        #     st.session_state.wolof_translation = "Traduction indisponible."

        # Afficher les résultats et le lecteur audio
        with st.chat_message("user"):
            st.markdown(f"🎤 (Audio): {st.session_state.transcribed_text}")
            st.audio(st.session_state.audio_for_playback, format="audio/wav")
            # st.markdown(f"**Traduction en Wolof :** {st.session_state.wolof_translation}") # Supprimé
        
        # Utiliser le texte transcrit comme prompt pour l'IA
        prompt = st.session_state.transcribed_text
        # Ajouter le message à l'historique de session pour l'affichage
        st.session_state.messages.append({"role": "user", "content": f"🎤 (Audio): {prompt}"})

    else:
        st.error("La transcription audio a échoué.")
        prompt = None

elif prompt_input:
    prompt = prompt_input
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
else:
    prompt = None


if prompt:
    # if not api_key:
    #     st.warning("API Key benötigt!")
    #     st.stop()
    
    try:
        # Inhalt vorbereiten
        content = [{"text": prompt}]
        
        # Traitement du fichier audio téléchargé (si le microphone n'a pas été utilisé)
        if uploaded_audio_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix=uploaded_audio_file.name.split('.')[-1]) as tmp_file:
                tmp_file.write(uploaded_audio_file.getvalue())
                tmp_file_path = tmp_file.name
            
            transcribed_text = transcribe_audio_with_gemini(tmp_file_path)
            os.remove(tmp_file_path) # Supprimer le fichier temporaire
            
            if transcribed_text:
                prompt = transcribed_text # Utiliser le texte transcrit comme prompt
                st.session_state.messages.append({"role": "user", "content": f"🎤 (Audio): {prompt}"})
                with st.chat_message("user"):
                    st.markdown(f"🎤 (Audio): {prompt}")
            else:
                st.error("La transcription audio a échoué.")
                st.stop()

        
        # Dateiinhalt hinzufügen
        if st.session_state.uploaded_content:
            if st.session_state.uploaded_content["type"] == "image":
                if "vision" not in model.lower():
                    st.error("Bitte ein Vision-Modell für Bilder auswählen!")
                    st.stop()
                content.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": encode_image(st.session_state.uploaded_content["content"])
                    }
                })
            elif st.session_state.uploaded_content["type"] == "text":
                content[0]["text"] += f"\n\n[File Content]\n{st.session_state.uploaded_content['content']}"
        
        # Nachricht zur Historie hinzufügen (si ce n'est pas déjà fait par l'audio)
        # if not uploaded_audio_file and not audio_bytes:
        #     st.session_state.messages.append({"role": "user", "content": prompt})
        #     with st.chat_message("user"):
        #         st.markdown(prompt)
        
        # Antwort generieren
        response = model_instance.generate_content(
            content,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens
            )
        )
        
        # Überprüfen, ob die Antwort gültig ist
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            st.error(f"API Error: La réponse a été bloquée en raison de problèmes de sécurité. Raison: {response.prompt_feedback.block_reason.name}")
        elif not response.candidates or response.candidates[0].finish_reason == "SAFETY":
            st.error("API Error: La réponse a été bloquée en raison de problèmes de sécurité.")
        else:
            # Antwort anzeigen
            with st.chat_message("assistant"):
                st.markdown(response.text)
                
                # # Générer et lire l'audio Wolof
                # try:
                #     tts_model = genai.GenerativeModel('gemini-2.5-flash') # Utiliser un modèle TTS
                #     tts_response = tts_model.generate_content(
                #         [WOLOF_TTS_PROMPT + response.text],
                #         config=types.GenerateContentConfig(
                #             response_modalities=["AUDIO"],
                #             speech_config=types.SpeechConfig(
                #                 voice_config=types.VoiceConfig(
                #                     prebuilt_voice_config=types.PrebuiltVoiceConfig(
                #                         voice_name='Kore'
                #                     )
                #                 )
                #             )
                #         )
                #     )
                #     
                #     if tts_response.prompt_feedback and tts_response.prompt_feedback.block_reason:
                #         st.error(f"API Error: La réponse a été bloquée en raison de: {tts_response.prompt_feedback.block_reason.name}")
                #     elif tts_response.candidates and tts_response.candidates[0].finish_reason == "SAFETY":
                #         safety_ratings = tts_response.candidates[0].safety_ratings
                #         blocked_categories = [rating.category.name for rating in safety_ratings if rating.blocked]
                #         st.error(f"API Error: La réponse a été bloquée en raison de problèmes de sécurité dans les catégories: {', '.join(blocked_categories)}")
                #     elif tts_response.candidates and tts_response.candidates[0].content.parts:
                #         audio_data = tts_response.candidates[0].content.parts[0].inline_data.data
                #         st.audio(audio_data, format="audio/wav")
                #     else:
                #         st.warning("Impossible de générer l'audio Wolof.")
                # except Exception as e:
                #     st.error(f"Erreur lors de la génération audio Wolof: {e}")

            st.session_state.messages.append({"role": "assistant", "content": response.text})
        
    except Exception as e:
        st.error(f"API Error: {str(e)}")
        if st.session_state.uploaded_content and "vision" not in model and st.session_state.uploaded_content["type"] == "image":
            st.error("Für Bilder einen Vision-fähigen Modell auswählen!")

# Instructions in the sidebar
with st.sidebar:
    st.markdown("""
    ## 📝 Instructions:
    1. Enter your Google AI API key
    2. Select a model (use vision models for image analysis)
    3. Adjust temperature and max tokens if needed
    4. Optional: Set a system prompt
    5. Upload an image (optional)
    6. Type your message and press Enter
    ### About
    🔗 [GitHub Profile](https://github.com/volkansah) | 
    📂 [Project Repository](https://github.com/volkansah/gemini-ai-chat) | 
    💬 [Soon](https://aicodecraft.io)
      """)
