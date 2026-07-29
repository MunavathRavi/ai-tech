from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.metrics import accuracy_score
from sklearn.metrics import recall_score

x = [[7],[15],[22],[20],[27],[30]]
y = [0,0,1,1,1,1]

model = LogisticRegression()

model.fit(x, y)

y_pred = model.predict(x)

print(y_pred)

print("Confusion Matrix:")
print(confusion_matrix(y, y_pred))

print("Accuracy:")
print(accuracy_score(y, y_pred))
print("recall_score")
print(recall_score(y,y_pred))