# oppsn =
n = int(input())
conut = 0
for i in range(1,n+1):
    if n%i==0:
        conut += 1
if conut == 2:
    print("prime number")
else:
    print("not a prome numer")