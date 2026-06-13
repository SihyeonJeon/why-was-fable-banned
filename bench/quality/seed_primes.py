def is_prime(n):
    # Correct but O(n). The task is to optimize WITHOUT changing behavior for any
    # integer (n < 2 and negatives are not prime; 2 and 3 are prime).
    if n < 2:
        return False
    i = 2
    while i < n:
        if n % i == 0:
            return False
        i += 1
    return True
