from flask import Flask, request, jsonify, render_template
import os
from werkzeug.utils import secure_filename

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain.chains import RetrievalQA

app = Flask(__name__)


os.environ["GROQ_API_KEY"] = "gsk"


UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB limit

ALLOWED_EXTENSIONS = {"pdf","jpg"}

vector_store = None

llm = ChatGroq(
    model_name="llama-3.1-8b-instant",
    temperature=0
)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def home():
    return render_template("index.html")


@app.route('/upload', methods=['POST'])
def upload_pdf():
    global vector_store

    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Only PDF files are allowed"}), 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    try:
        
        loader = PyPDFLoader(file_path)
        documents = loader.load()

        if not documents:
            return jsonify({"error": "PDF has no readable content"}), 400

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        docs = splitter.split_documents(documents)

        if not docs:
            return jsonify({"error": "Text splitting failed"}), 500

        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        vector_store = FAISS.from_documents(docs, embeddings)

        return jsonify({"message": "PDF processed successfully"})

    except Exception as e:
        return jsonify({"error": f"❌ {str(e)}"}), 500


@app.route('/ask', methods=['POST'])
def ask_question():
    global vector_store

    if vector_store is None:
        return jsonify({"error": "Upload a PDF first"}), 400

    try:
        data = request.get_json(force=True)
        query = data.get("question", "").strip()

        if not query:
            return jsonify({"error": "Question is required"}), 400

        retriever = vector_store.as_retriever(search_kwargs={"k": 5})

        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=retriever
        )

        result = qa_chain.invoke({"query": query})

        return jsonify({"answer": result.get("result", "No answer found")})

    except Exception as e:
        return jsonify({"error": f"❌ {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)

    