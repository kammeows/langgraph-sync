import bs4
import requests
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import ChatOllama, OllamaEmbeddings
# Using langgraph for a robust agent loop
from langchain.agents import create_agent

# 1. Setup Document Loading and Splitting
def load_web_page(url: str, bs_kwargs: dict | None = None) -> list[Document]:
    response = requests.get(url)
    response.raise_for_status()
    soup = bs4.BeautifulSoup(response.text, "html.parser", **(bs_kwargs or {}))
    return [Document(page_content=soup.get_text(), metadata={"source": url})]

docs = load_web_page(
    "https://lilianweng.github.io/posts/2023-06-23-agent/",
    bs_kwargs={
        "parse_only": bs4.SoupStrainer(
            class_=("post-content", "post-title", "post-header")
        )
    },
)

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
all_splits = text_splitter.split_documents(docs)

# 2. Initialize Embeddings and Vector Store
# (Chroma.from_documents automatically adds the documents)
embeddings = OllamaEmbeddings(model="nomic-embed-text")
vector_store = Chroma.from_documents(
    documents=all_splits,
    embedding=embeddings,
    collection_name="rag_tutorial"
)

# 3. Define the Tool FIRST so it exists when referenced
@tool(response_format="content_and_artifact")
def retrieve_context(query: str):
    """Retrieve information to help answer a query from the database."""
    retrieved_docs = vector_store.similarity_search(query, k=2)
    serialized = "\n\n".join(
        f"Source: {doc.metadata}\nContent: {doc.page_content}"
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs

tools = [retrieve_context]

# 4. Initialize LLM
model = ChatOllama(model="gemma4:e2b-it-q4_K_M", temperature=0)

# 5. Build and Run the Agent Loop
prompt = (
    "You are a helpful assistant. You have access to a tool that retrieves context from a blog post. "
    "Always use the retrieve_context tool to find answers before responding. "
    "If the retrieved context does not contain relevant information, say that you don't know."
)

# create_react_agent binds tools and manages the loop natively
agent = create_agent(model, tools, system_prompt=prompt)

query = "What is task decomposition?"

# Stream the agent's progress
for chunk in agent.stream({"messages": [{"role": "user", "content": query}]}):
    for node, value in chunk.items():
        print(f"\n--- Node: {node} ---")
        if "messages" in value:
            value["messages"][-1].pretty_print()