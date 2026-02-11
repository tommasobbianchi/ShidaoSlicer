#!/usr/bin/env python3
"""
Test script to verify belt transform math and identify double rotation issues.
"""
import math

def mat_mult(A, v):
    """Multiply 3x3 matrix A by 3D vector v"""
    return [
        A[0][0]*v[0] + A[0][1]*v[1] + A[0][2]*v[2],
        A[1][0]*v[0] + A[1][1]*v[1] + A[1][2]*v[2],
        A[2][0]*v[0] + A[2][1]*v[1] + A[2][2]*v[2]
    ]

def mat_mult_mat(A, B):
    """Multiply two 3x3 matrices"""
    result = [[0]*3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            for k in range(3):
                result[i][j] += A[i][k] * B[k][j]
    return result

# Forward transform from belt_transform.ini
forward = [
    [1, 0, 0],
    [0, 0.70710678, -0.70710678],
    [0, 0.70710678, 0.70710678]
]

# Inverse transform from belt_transform.ini
inverse = [
    [1, 0, 0],
    [0, 0.70710678, 0.70710678],
    [0, -0.70710678, 0.70710678]
]

print("=== Belt Transform Math Verification ===\n")

# Test with a point: 20mm cube corner at (10, 10, 10)
point = [10, 10, 10]
print(f"Original point (20mm cube corner): {point}")

# Apply forward transform
point_forward = mat_mult(forward, point)
print(f"\nAfter forward transform (+45° X-rotation):")
print(f"  Point: [{point_forward[0]:.2f}, {point_forward[1]:.2f}, {point_forward[2]:.2f}]")
print(f"  Y: {point[1]:.2f} → {point_forward[1]:.2f} (change: {point_forward[1]-point[1]:.2f})")
print(f"  Z: {point[2]:.2f} → {point_forward[2]:.2f} (change: {point_forward[2]-point[2]:.2f})")

# Apply forward TWICE (simulating double rotation bug)
point_double = mat_mult(forward, point_forward)
print(f"\nAfter DOUBLE forward transform (90° bug):")
print(f"  Point: [{point_double[0]:.2f}, {point_double[1]:.2f}, {point_double[2]:.2f}]")
print(f"  Y: {point[1]:.2f} → {point_double[1]:.2f} (change: {point_double[1]-point[1]:.2f})")
print(f"  Z: {point[2]:.2f} → {point_double[2]:.2f} (change: {point_double[2]-point[2]:.2f})")

# Apply inverse to single forward
point_back = mat_mult(inverse, point_forward)
print(f"\nAfter forward then inverse (correct):")
print(f"  Point: [{point_back[0]:.2f}, {point_back[1]:.2f}, {point_back[2]:.2f}]")
print(f"  Matches original: {all(abs(a-b) < 0.01 for a,b in zip(point, point_back))}")

# Test what happens with double forward then single inverse
point_double_inv = mat_mult(inverse, point_double)
print(f"\nAfter DOUBLE forward then inverse (if bug exists):")
print(f"  Point: [{point_double_inv[0]:.2f}, {point_double_inv[1]:.2f}, {point_double_inv[2]:.2f}]")
print(f"  This is what G-code would output with double rotation bug")

# Test composition
identity = mat_mult_mat(inverse, forward)
print(f"\nInverse * Forward:")
for row in identity:
    print(f"  [{row[0]:.4f}, {row[1]:.4f}, {row[2]:.4f}]")
is_identity = all(abs(identity[i][i] - 1) < 0.01 and
                  all(abs(identity[i][j]) < 0.01 for j in range(3) if i != j)
                  for i in range(3))
print(f"  Is identity: {is_identity}")
