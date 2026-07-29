from flask import Flask, request, jsonify
from flask_cors import CORS
import pickle

app = Flask(__name__)
CORS(app)

# Load saved model
vectorizer = pickle.load(open("/Users/munavathsai/fake-job-detection/backend/model/count_vectorizer.pkl", "rb"))
model = pickle.load(open("/Users/munavathsai/fake-job-detection/backend/model/nb_classifier.pkl", "rb"))

@app.route("/")
def home():
    return "Fake Job Detection API Running"

@app.route("/predict", methods=["POST"])
def predict():

    data = request.json

    text = data.get("description", "")

    X = vectorizer.transform([text])

    prediction = model.predict(X)[0]
    return jsonify({
        "fraudulent": int(prediction),
    })


if __name__ == "__main__":
    app.run(debug=True)

#  % curl -X POST http://127.0.0.1:5000/predict \
# -H "Content-Type: application/json" \
# -d '{"url":"https://oes.onpassive.com/auth"}'
# {
#   "fraudulent": 0.   we cheek the thermimal in code
# }
# munavathsai@Mac ~ % 
