def moving_average(values, window=3):
    """Return the moving average of a list of numbers."""
    if window <= 0:
        raise ValueError("window must be positive")
    result = []
    for i in range(len(values) - window + 1):
        chunk = values[i:i + window]
        result.append(sum(chunk) / window)
    return result


if __name__ == "__main__":
    print(moving_average([10, 20, 30, 40, 50], 3))
