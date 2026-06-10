from openai import OpenAI

client = OpenAI()

response = client.models.list()

print("Connected!")